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
from .os_bridge import browse_workspace, open_terminal, open_vscode
from .reporter import DEFAULT_BACKEND_URL, DEFAULT_REPORT_INTERVAL_SEC, reporter_loop
from .tmux_scanner import scan_sessions

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 30083

# 대시보드 origin 화이트리스트. 중앙 호스팅 도메인 추가시 여기에 함께.
ALLOWED_ORIGINS = {
    "http://localhost:30080",
    "http://127.0.0.1:30080",
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


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ──────────────────────────────────────────────────────────────────────────────


async def _start_reporter(app: web.Application) -> None:
    backend_url = os.environ.get("AIDESK_BACKEND_URL", DEFAULT_BACKEND_URL)
    interval = float(
        os.environ.get("AIDESK_REPORT_INTERVAL_SEC", DEFAULT_REPORT_INTERVAL_SEC)
    )
    log.info("reporter starting: backend=%s interval=%.1fs", backend_url, interval)
    app["reporter_task"] = asyncio.create_task(reporter_loop(backend_url, interval))


async def _stop_reporter(app: web.Application) -> None:
    task = app.get("reporter_task")
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def build_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/local-info", local_info)
    app.router.add_post("/api/open-terminal", open_terminal_handler)
    app.router.add_post("/api/open-vscode", open_vscode_handler)
    app.router.add_post("/api/browse-workspace", browse_workspace_handler)
    # CORS preflight 는 미들웨어가 처리 — OPTIONS 라우트도 등록해야 404 안 남.
    app.router.add_route("OPTIONS", "/api/{tail:.*}", lambda r: web.Response(status=204))
    app.on_startup.append(_start_reporter)
    app.on_cleanup.append(_stop_reporter)
    return app


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    web.run_app(build_app(), host=host, port=port, access_log=None)
