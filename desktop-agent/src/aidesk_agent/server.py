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
from .claude.bootstrap import bootstrap_agent
from .claude.scanner import scan_workspaces
from .vscode.code_server import DEFAULT_PORT as CODE_SERVER_PORT
from .vscode.code_server import start_code_server, stop_code_server
from .vscode import open_vscode
from .terminal import ensure_iterm_dynamic_profile, open_terminal
from .workspace import browse_file, browse_workspace, cleanup_agent, scope_workspace
# 임베드 터미널 사이드 패널 비활성화에 맞춰 pty WebSocket handler 도 보류.
# 복원하려면 이 import 와 아래의 라우터 등록 두 곳을 같이 주석 해제.
# from .tmux.pty_bridge import terminal_handler
from .reporter import DEFAULT_BACKEND_URL, DEFAULT_REPORT_INTERVAL_SEC, reporter_loop
from .tmux import consumer_loop, scan_sessions
from .claude.action_hook import auto_install_on_startup as action_hook_auto_install
from .claude.prompt_hook import auto_install_on_startup as prompt_hook_auto_install
from .claude.usage import (
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


async def scope_workspace_handler(request: web.Request) -> web.Response:
    """A2A 워크스페이스 검증 + ~/.claude.json 의 kaflix-* MCP scope 이동.

    백엔드(도커)가 호스트 파일시스템에 접근 못 하므로 host.docker.internal:30083 으로 호출.
    body: { "newWorkspace": "<absolute path>", "oldWorkspace": "<previous path or empty>" }
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    new_workspace = (body.get("newWorkspace") or "").strip()
    old_workspace = (body.get("oldWorkspace") or "").strip()
    purge_previous_history = bool(body.get("purgePreviousHistory", False))
    me_tmux_session = (body.get("meTmuxSession") or "").strip() or None
    rc, msg, abs_path = scope_workspace(
        new_workspace,
        old_workspace or None,
        purge_previous_history,
        me_tmux_session,
    )
    status = 200 if rc == 0 else (400 if rc in (1, 2) else 500)
    return web.json_response(
        {"rc": rc, "message": msg, "absolutePath": abs_path}, status=status
    )


async def browse_file_handler(request: web.Request) -> web.Response:
    """파일 선택 다이얼로그 — body.prompt 로 프롬프트 텍스트 커스터마이즈 가능."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    prompt = (body.get("prompt") if isinstance(body, dict) else None) or "파일을 선택하세요"
    rc, path_or_msg = browse_file(prompt)
    if rc != 0:
        return web.json_response({"rc": rc, "message": path_or_msg}, status=500)
    return web.json_response({"rc": 0, "path": path_or_msg})


async def cleanup_agent_handler(request: web.Request) -> web.Response:
    """에이전트 삭제 시 프론트가 호출 — tmux 세션 + Terminal 윈도우 정리.

    purgeHistory=true 이면 ~/.claude/projects/{escaped-cwd}/ 의 jsonl 대화 기록까지 같이 삭제 —
    같은 워크스페이스 경로로 새 에이전트 생성했을 때 옛 대화가 살아오는 걸 차단.
    """
    body = await request.json()
    tmux_session = (body.get("tmuxSession") or "").strip()
    workspace_dir = (body.get("workspaceDir") or "").strip()
    purge_history = bool(body.get("purgeHistory") or False)
    rc, msg = cleanup_agent(tmux_session, workspace_dir or None, purge_history)
    return web.json_response({"rc": rc, "message": msg})


async def agent_bootstrap_handler(request: web.Request) -> web.Response:
    """신규 AI 생성 직후 프론트가 호출 — .claude/settings.local.json + headless tmux 시작.

    이 둘이 끝나야 사용자가 외부/임베드 터미널을 안 열어도 다른 AI 와 즉시 통신 가능.
    """
    body = await request.json()
    workspace_dir = (body.get("workspaceDir") or "").strip()
    tmux_session = (body.get("tmuxSession") or "").strip()
    agent_name = (body.get("agentName") or "").strip()
    if not workspace_dir or not tmux_session:
        return web.json_response(
            {"rc": 2, "message": "workspaceDir 와 tmuxSession 이 모두 필요합니다."},
            status=400,
        )
    result = bootstrap_agent(workspace_dir, tmux_session, agent_name)
    return web.json_response({"rc": 0, "message": "ok", **result})


async def check_tmux_handler(request: web.Request) -> web.Response:
    """백엔드의 메시지 pre-flight 체크용 — 지정 tmux 세션이 실제 호스트에 살아있는지 확인.

    body: {tmuxSession: "aidesk-xxx"}
    response: {alive: bool, reason: string}
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    tmux_session = (body.get("tmuxSession") or "").strip() if isinstance(body, dict) else ""
    if not tmux_session:
        return web.json_response({"alive": False, "reason": "tmuxSession empty"})
    import subprocess
    try:
        proc = subprocess.run(
            ["tmux", "has-session", "-t", tmux_session],
            capture_output=True, timeout=2.0,
        )
        if proc.returncode == 0:
            return web.json_response({"alive": True, "reason": ""})
        return web.json_response({"alive": False, "reason": "tmux session not found on host"})
    except (subprocess.TimeoutExpired, OSError) as e:
        return web.json_response({"alive": False, "reason": f"tmux check error: {e}"})


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
    # iTerm Dynamic Profile 'AI Desk' 자동 생성 — Title Components 만 Session Name 으로
    # override 한 derivative profile. 외부 터미널 열기 시 이 profile 사용 → AI 이름이
    # title bar 에 표시됨. iTerm 미설치 환경이면 noop.
    ensure_iterm_dynamic_profile()
    # Claude Code statusLine 후크 — 미설치/옛 경로면 자동 등록. 다른 명령이 점유 중이면 보호.
    usage_auto_install()
    # Claude Code 응답 대기 감지 훅 (AskUserQuestion / Notification / Stop 등) 자동 등록.
    prompt_hook_auto_install()
    # Claude Code mutation 감사 훅 (Write/Edit/Bash/DB MCP) 자동 등록.
    action_hook_auto_install()
    app["reporter_task"] = asyncio.create_task(reporter_loop(backend_url, interval))
    app["sse_task"] = asyncio.create_task(consumer_loop(backend_url))
    # 자체 채널 모델 (2026-05~) 도입 후 케플릭스 사이드카 SSE 구독 (kaflix pump) 폐기.
    # 사내 동료 메시지는 우리 backend SSE 가 reporter_task / sse_task 흐름과 동일 경로로 도달.
    # 임베드 VSCode (code-server) — 대시보드의 사이드 패널이 비활성된 상태라 spawn 도 보류.
    # 30082 포트 + brew install 단계 비용 절감. 복원하려면 아래 한 줄 주석만 해제.
    # app["code_server_proc"] = await start_code_server()


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
    # code-server 자동 spawn 비활성 상태 — 정리할 proc 도 없음. 복원 시 같이 풀기.
    # await stop_code_server(app.get("code_server_proc"))


def build_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/local-info", local_info)
    app.router.add_post("/api/open-terminal", open_terminal_handler)
    app.router.add_post("/api/open-vscode", open_vscode_handler)
    app.router.add_post("/api/browse-workspace", browse_workspace_handler)
    app.router.add_post("/api/scope-workspace", scope_workspace_handler)
    app.router.add_post("/api/browse-file", browse_file_handler)
    app.router.add_post("/api/cleanup-agent", cleanup_agent_handler)
    app.router.add_post("/api/agents/bootstrap", agent_bootstrap_handler)
    app.router.add_post("/api/check-tmux", check_tmux_handler)
    app.router.add_get("/api/code-server", code_server_status_handler)
    app.router.add_get("/api/usage/local", usage_local_handler)
    app.router.add_post("/api/usage/install-statusline", usage_install_statusline_handler)
    # app.router.add_get("/api/terminal", terminal_handler)  # 임베드 터미널 비활성
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
