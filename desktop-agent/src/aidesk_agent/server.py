"""AI Desk Desktop Agent — aiohttp 기반 로컬 HTTP 리스너.

브라우저(중앙 호스팅 대시보드) ↔ 로컬 OS 사이의 IPC 다리 역할.
비즈니스 로직은 중앙 백엔드(Spring Boot) 가 담당하고, 본 모듈은 본인 Mac
자원만 조작한다.
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from . import __version__
from .claude_scanner import scan_workspaces
from .code_server import DEFAULT_PORT as CODE_SERVER_PORT
from .code_server import start_code_server, stop_code_server
from .os_bridge import browse_workspace, cleanup_agent, open_terminal, open_vscode
from .pty_bridge import terminal_handler
from .reporter import DEFAULT_BACKEND_URL, DEFAULT_REPORT_INTERVAL_SEC, reporter_loop
from .sse_consumer import consumer_loop
from .tmux_scanner import scan_sessions
from .usage import (
    auto_install_on_startup as usage_auto_install,
    get_local_usage,
    install_statusline_hook,
)

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 30083

# 대시보드 origin 화이트리스트. 환경변수 AIDESK_EXTRA_ORIGINS (콤마 구분) 로 운영 도메인 추가.
_DEFAULT_ORIGINS = {
    "http://localhost:30080",
    "http://127.0.0.1:30080",
}
ALLOWED_ORIGINS = _DEFAULT_ORIGINS | {
    o.strip() for o in os.environ.get("AIDESK_EXTRA_ORIGINS", "").split(",") if o.strip()
}


# ──────────────────────────────────────────────────────────────────────────────
# CORS 미들웨어
# ──────────────────────────────────────────────────────────────────────────────


@web.middleware
async def cors_middleware(request: web.Request, handler):
    origin = request.headers.get("Origin", "")
    is_preflight = request.method == "OPTIONS"

    if is_preflight:
        resp = web.Response(status=204)
    else:
        resp = await handler(request)

    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Max-Age"] = "600"
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# 핸들러
# ──────────────────────────────────────────────────────────────────────────────


async def health(_: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "version": __version__,
            "service": "aidesk-agent",
        }
    )


async def local_info(_: web.Request) -> web.Response:
    workspaces = [w.as_dict() for w in scan_workspaces()]
    tmux = [s.as_dict() for s in scan_sessions()]
    return web.json_response(
        {
            "workspaces": workspaces,
            "tmuxSessions": tmux,
        }
    )


async def open_terminal_handler(request: web.Request) -> web.Response:
    body = await request.json()
    workspace_dir = (body.get("workspaceDir") or "").strip()
    tmux_session = (body.get("tmuxSession") or "").strip()
    title = (body.get("title") or "").strip()
    rc, msg = open_terminal(workspace_dir, tmux_session, title)
    status = 200 if rc == 0 else (400 if rc == 2 else 500)
    return web.json_response({"rc": rc, "message": msg}, status=status)


async def open_vscode_handler(request: web.Request) -> web.Response:
    body = await request.json()
    workspace_dir = (body.get("workspaceDir") or "").strip()
    rc, msg = open_vscode(workspace_dir)
    status = 200 if rc == 0 else (400 if rc == 2 else 500)
    return web.json_response({"rc": rc, "message": msg}, status=status)


async def browse_workspace_handler(_: web.Request) -> web.Response:
    rc, path_or_msg = browse_workspace()
    if rc != 0:
        return web.json_response({"rc": rc, "message": path_or_msg}, status=500)
    # 빈 문자열 = 사용자 취소 (정상 응답)
    return web.json_response({"rc": 0, "path": path_or_msg})


async def cleanup_agent_handler(request: web.Request) -> web.Response:
    """에이전트 삭제 시 프론트가 호출 — tmux 세션 + Terminal 윈도우 정리."""
    body = await request.json()
    tmux_session = (body.get("tmuxSession") or "").strip()
    rc, msg = cleanup_agent(tmux_session)
    return web.json_response({"rc": rc, "message": msg})


async def usage_local_handler(_: web.Request) -> web.Response:
    """프론트 LocalUsageBar 가 사용 — 호스트의 ~/.claude/aidesk-usage/ 에서 최신 사용량 노출."""
    return web.json_response(get_local_usage())


async def usage_install_statusline_handler(_: web.Request) -> web.Response:
    """프론트의 [수동 설치] 버튼 — settings.json 에 statusLine 후크 주입."""
    rc = install_statusline_hook()
    if rc == 0:
        return web.json_response({"rc": 0, "message": "ok"})
    msg = (
        "statusline 스크립트(adesk-cli/bin/aidesk-statusline.cjs)를 찾지 못했습니다."
        if rc == 1
        else "~/.claude/settings.json 갱신에 실패했습니다."
    )
    return web.json_response({"rc": rc, "message": msg}, status=500)


async def code_server_status_handler(request: web.Request) -> web.Response:
    """대시보드의 임베드 VSCode 가 사용 — Helper 가 띄운 code-server 의 URL + alive."""
    proc = request.app.get("code_server_proc")
    alive = proc is not None and proc.returncode is None
    return web.json_response(
        {
            "url": f"http://localhost:{CODE_SERVER_PORT}",
            "alive": alive,
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ──────────────────────────────────────────────────────────────────────────────


async def _start_background_tasks(app: web.Application) -> None:
    backend_url = os.environ.get("AIDESK_BACKEND_URL", DEFAULT_BACKEND_URL)
    interval = float(
        os.environ.get("AIDESK_REPORT_INTERVAL_SEC", DEFAULT_REPORT_INTERVAL_SEC)
    )
    log.info("background tasks starting: backend=%s interval=%.1fs", backend_url, interval)
    # Claude Code statusLine 후크 — 미설치/옛 경로면 자동 등록. 다른 명령이 점유 중이면 보호.
    usage_auto_install()
    app["reporter_task"] = asyncio.create_task(reporter_loop(backend_url, interval))
    app["sse_task"] = asyncio.create_task(consumer_loop(backend_url))
    # code-server 도 같이 spawn — 부재 시 brew install 자동 시도. 실패해도 다른 기능엔 영향 없음.
    app["code_server_proc"] = await start_code_server()


async def _stop_background_tasks(app: web.Application) -> None:
    for key in ("reporter_task", "sse_task"):
        task = app.get(key)
        if task is None:
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await stop_code_server(app.get("code_server_proc"))


def build_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/local-info", local_info)
    app.router.add_post("/api/open-terminal", open_terminal_handler)
    app.router.add_post("/api/open-vscode", open_vscode_handler)
    app.router.add_post("/api/browse-workspace", browse_workspace_handler)
    app.router.add_post("/api/cleanup-agent", cleanup_agent_handler)
    app.router.add_get("/api/code-server", code_server_status_handler)
    app.router.add_get("/api/usage/local", usage_local_handler)
    app.router.add_post("/api/usage/install-statusline", usage_install_statusline_handler)
    app.router.add_get("/api/terminal", terminal_handler)
    # CORS preflight 는 미들웨어가 처리 — OPTIONS 라우트도 등록해야 404 안 남.
    app.router.add_route("OPTIONS", "/api/{tail:.*}", lambda r: web.Response(status=204))
    app.on_startup.append(_start_background_tasks)
    app.on_cleanup.append(_stop_background_tasks)
    return app


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    web.run_app(build_app(), host=host, port=port, access_log=None)
