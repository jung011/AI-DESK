"""AI Desk Desktop Agent — aiohttp 기반 로컬 HTTP 리스너.

브라우저(중앙 호스팅 대시보드) ↔ 로컬 OS 사이의 IPC 다리 역할.
비즈니스 로직은 중앙 백엔드(Spring Boot) 가 담당하고, 본 모듈은 본인 Mac
자원만 조작한다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import plistlib
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web

from . import __version__
from .claude.bootstrap import bootstrap_agent, ensure_bot_adapter, start_claude_with_mode
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
from .watchdog import watchdog_loop
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

# --- 단일 진실: AIDESK_HUB_URL ---
# 옛엔 AIDESK_BACKEND_URL + AIDESK_EXTRA_ORIGINS 두 변수가 별도 — URL 한 번 바꿀 때 두 군데
# 일관성 유지가 어려웠다 (path 포함 vs 제거 등 결함 빈발). 이제 HUB_URL 하나만 보면 된다:
#   AIDESK_HUB_URL=<frontend URL>  ← 사용자가 setup 모달에서 입력하는 *동일한 값*
# 옛 키 (AIDESK_BACKEND_URL/AIDESK_EXTRA_ORIGINS) 는 backward compat fallback 으로만 인식.
def _resolve_hub_url() -> str:
    return (
        os.environ.get("AIDESK_HUB_URL")
        or os.environ.get("AIDESK_BACKEND_URL")
        or "http://localhost:30081"
    ).rstrip("/")


def _origin_of(url: str) -> str:
    """URL 에서 path 제거된 *origin* (scheme://host[:port]) 만 반환 — brower Origin 헤더 매칭용."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else url


# 대시보드 origin 화이트리스트.
_DEFAULT_ORIGINS = {
    "http://localhost:30080",
    "http://127.0.0.1:30080",
}
ALLOWED_ORIGINS = (
    _DEFAULT_ORIGINS
    | ({_origin_of(_resolve_hub_url())} if _resolve_hub_url() else set())
    # backward compat — 옛 deploy 에서 콤마-구분 EXTRA_ORIGINS 박은 경우.
    | {o.strip() for o in os.environ.get("AIDESK_EXTRA_ORIGINS", "").split(",") if o.strip()}
)

# 중앙서버 URL 이 바뀌거나 새 동료가 첫 진입할 때 brower 의 origin 이 helper 의
# ALLOWED_ORIGINS 에 아직 없을 수 있다. helper-install 페이지 흐름에 쓰이는 health /
# local-info / setup 세 endpoint 는 화이트리스트 우회로 *모든 origin* 을 허용한다.
# 그 외 (browse, scope, agents/bootstrap 등) 는 기존 정책 유지 — 정상 origin 만.
_OPEN_ORIGIN_PATHS = {"/api/setup", "/api/local-info", "/api/health"}

_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.aidesk.agent.plist"
_CLAUDE_JSON_PATH = Path.home() / ".claude.json"
_HUB_URL_RE = re.compile(r"^https?://[\w\.\-]+(?::\d+)?(?:/[\w\.\-/]*)?/?$")


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

    allow = origin in ALLOWED_ORIGINS or request.path in _OPEN_ORIGIN_PATHS
    if allow and origin:
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
            # 현재 helper 가 가리키는 중앙서버 — HUB_URL 단일 진실로 통합.
            "currentBackendUrl": _resolve_hub_url(),
            "currentExtraOrigins": sorted(o for o in ALLOWED_ORIGINS if o not in _DEFAULT_ORIGINS),
        }
    )


def _derive_hub_origin(hub_url: str) -> str:
    """`http://IP:30081` -> `http://IP:30080` 같이 backend(:30081) URL 에서 frontend(:30080) origin 추출.
    이미 :30080 또는 다른 form 이면 그대로 통과."""
    # 가장 단순한 규칙 — 30081 -> 30080 치환. 옛 사용자 환경 보장.
    if hub_url.rstrip("/").endswith(":30081"):
        return hub_url.rstrip("/")[:-len(":30081")] + ":30080"
    return hub_url.rstrip("/")


def _apply_setup(hub_url: str) -> tuple[int, str]:
    """plist + ~/.claude.json 갱신. helper 자신 재로드는 응답 후 별도 task 에서."""
    hub_url = hub_url.rstrip("/")
    if not _HUB_URL_RE.match(hub_url + "/"):
        return 1, "hubUrl 형식이 올바르지 않습니다 (예: http://10.0.0.1:30080)"
    # 30080 (frontend) URL 받아서 30081 (backend) 로 자동 매핑.
    frontend_origin = _derive_hub_origin(hub_url) if hub_url.endswith(":30081") else hub_url
    backend_url = (
        hub_url
        if hub_url.endswith(":30081")
        else (frontend_origin[:-len(":30080")] + ":30081" if frontend_origin.endswith(":30080") else frontend_origin)
    )

    # 1) plist 갱신 — 단일 진실 AIDESK_HUB_URL 만 저장. 옛 키는 마이그레이션 잔재라 제거.
    if not _PLIST_PATH.exists():
        return 2, f"LaunchAgent plist 가 없습니다: {_PLIST_PATH}"
    try:
        with open(_PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        env = plist.setdefault("EnvironmentVariables", {})
        env["AIDESK_HUB_URL"] = backend_url
        env.pop("AIDESK_BACKEND_URL", None)
        env.pop("AIDESK_EXTRA_ORIGINS", None)
        with open(_PLIST_PATH, "wb") as f:
            plistlib.dump(plist, f)
    except (OSError, plistlib.InvalidFileException) as e:
        return 3, f"plist 갱신 실패: {e}"

    # 2) ~/.claude.json 의 aidesk-channel mcp env.AIDESK_API_URL 갱신
    try:
        with open(_CLAUDE_JSON_PATH) as f:
            cdata = json.load(f)
        servers = cdata.setdefault("mcpServers", {})
        ac = servers.setdefault("aidesk-channel", {})
        ac_env = ac.setdefault("env", {})
        ac_env["AIDESK_API_URL"] = backend_url
        with open(_CLAUDE_JSON_PATH, "w") as f:
            json.dump(cdata, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except (OSError, json.JSONDecodeError) as e:
        return 4, f"~/.claude.json 갱신 실패: {e}"

    return 0, backend_url


def _spawn_detached_reload() -> None:
    """plist 갱신 후 launchctl bootout + bootstrap 으로 새 env 로 재기동.
    helper 자기 자신을 죽이는 작업이므로 *detached subprocess* 로 띄워야 한다 —
    self-bootout 후에도 그 sh 가 살아남아 bootstrap 까지 완수."""
    uid = os.getuid()
    label = f"gui/{uid}/com.aidesk.agent"
    plist_path = str(_PLIST_PATH)
    try:
        subprocess.Popen(
            [
                "/bin/sh", "-c",
                f"sleep 1; launchctl bootout {label} 2>/dev/null; "
                f"sleep 1; launchctl bootstrap gui/{uid} {plist_path}",
            ],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        log.warning("setup reload: spawn failed: %s", e)


async def setup_handler(request: web.Request) -> web.Response:
    """동료가 brower 에서 *중앙서버 URL* 입력 → helper 가 plist + ~/.claude.json 자동 갱신 + 재로드.

    body: { hubUrl: "http://<IP>:30080" or "http://<IP>:30081" }
    응답:  { rc, message, currentBackendUrl, currentExtraOrigins }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"rc": 1, "message": "JSON body required"}, status=400)
    hub_url = (body.get("hubUrl") or "").strip() if isinstance(body, dict) else ""
    if not hub_url:
        return web.json_response({"rc": 1, "message": "hubUrl required"}, status=400)
    rc, msg_or_backend = _apply_setup(hub_url)
    if rc != 0:
        return web.json_response({"rc": rc, "message": msg_or_backend}, status=400)
    backend_url = msg_or_backend
    # 응답 후 detached sh 가 launchctl bootout + bootstrap — helper 가 죽어도 sh 가 살아남음.
    _spawn_detached_reload()
    return web.json_response({
        "rc": 0,
        "message": "ok",
        "currentBackendUrl": backend_url,
        "currentExtraOrigins": [_derive_hub_origin(hub_url) if hub_url.endswith(":30081") else hub_url],
    })


async def open_terminal_handler(request: web.Request) -> web.Response:
    """외부 터미널 열기 — tmux 세션 살아있으면 attach + 포커스, 죽었으면 모드 선택 요구.

    body:
      workspaceDir, tmuxSession, title : 필수
      mode (optional)                  : 'claude' / 'telegram' / 'custom'
      customOpts (optional)            : mode='custom' 일 때 claude 의 추가 옵션
      agentName, workroleFile (optional): 첫 부팅 시 identity/workrole 주입에 사용

    응답:
      - tmux 살아있음 → 기존 open_terminal 호출 (attach + 포커스). 200 rc=0
      - tmux 부재 + mode 미제공 → 412 needsModeSelection=true (frontend 가 팝업 띄움)
      - tmux 부재 + mode 제공 → start_claude_with_mode 로 새로 띄운 뒤 open_terminal. 200
    """
    body = await request.json()
    workspace_dir = (body.get("workspaceDir") or "").strip()
    tmux_session = (body.get("tmuxSession") or "").strip()
    title = (body.get("title") or "").strip()
    mode = (body.get("mode") or "").strip()
    custom_opts = (body.get("customOpts") or "").strip()
    agent_name = (body.get("agentName") or "").strip()
    workrole_file = (body.get("workroleFile") or "").strip()
    # PoC v1 — 봇 어댑터 spawn 시 backend WS 인증용 agentId 필요. frontend 가 본 카드의 agentId 전달.
    agent_id = (body.get("agentId") or "").strip()

    if not workspace_dir or not tmux_session:
        return web.json_response(
            {"rc": 2, "message": "workspaceDir 와 tmuxSession 이 모두 필요합니다."},
            status=400,
        )

    session_alive = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session],
        capture_output=True,
    ).returncode == 0

    if not session_alive:
        if not mode:
            # frontend 가 이 신호를 보고 *터미널 모드 선택 모달* 을 띄운다.
            return web.json_response(
                {
                    "rc": 3,
                    "message": "tmux session not running — mode selection required",
                    "needsModeSelection": True,
                },
                status=412,
            )
        start_result = start_claude_with_mode(
            workspace_dir, tmux_session, mode, custom_opts, agent_name, workrole_file, agent_id,
        )
        if not start_result.get("tmuxStarted"):
            return web.json_response(
                {"rc": 1, "message": "tmux start failed", **start_result},
                status=500,
            )
    elif agent_id:
        # tmux 살아있는 케이스 — start_claude_with_mode 안 거치므로 봇 어댑터 별도 보장.
        # ensure_bot_adapter 는 idempotent — 이미 동작 중이면 skip.
        ensure_bot_adapter(agent_id, tmux_session)

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
    """(me) 워크스페이스 검증 + ~/.claude.json 의 projects entry 마킹.

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
    """신규 AI 생성 직후 프론트가 호출 — workspace trust + .claude/settings.local.json 권한 부여만.

    옛 정책: 여기서 headless tmux + claude 자동 시작 → 외부 터미널 안 열어도 즉시 통신 가능.
    새 정책: 실제 claude 시작은 사용자가 *외부 터미널 열기* 에서 모드를 고른 시점에 일어남
    (open_terminal_handler → start_claude_with_mode). 그 전엔 다른 AI 가 보낸 메시지가
    옵션 2 분기로 즉시 failed 처리된다.
    """
    body = await request.json()
    workspace_dir = (body.get("workspaceDir") or "").strip()
    tmux_session = (body.get("tmuxSession") or "").strip()
    agent_name = (body.get("agentName") or "").strip()
    # workroleFile 은 옛엔 helper 가 backend 에 인증 없이 GET 했지만 그 endpoint 가 인증 가드 안에
    # 있어 항상 빈 응답 → 프롬프트 누락. frontend 가 인증 cookie 로 미리 조회해서 같이 넘긴다.
    workrole_file = (body.get("workroleFile") or "").strip()
    if not workspace_dir or not tmux_session:
        return web.json_response(
            {"rc": 2, "message": "workspaceDir 와 tmuxSession 이 모두 필요합니다."},
            status=400,
        )
    result = bootstrap_agent(workspace_dir, tmux_session, agent_name, workrole_file)
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
    backend_url = _resolve_hub_url()
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
    # 좀비 self-heal — SSE idle 90s+ 시 process self-kill → LaunchAgent KeepAlive 가 재기동.
    app["watchdog_task"] = asyncio.create_task(watchdog_loop())
    # 봇 어댑터 자가치유 — 30s 주기로 살아있는지 점검. 죽었으면 skip set 에서 빼서
    # sse_consumer 가 fallback 으로 last-mile 인수. 다음 ensure_bot_adapter 호출 시 재spawn.
    app["bot_adapter_monitor_task"] = asyncio.create_task(_bot_adapter_monitor_loop())
    # 자체 채널 모델 (2026-05~) 도입 후 케플릭스 사이드카 SSE 구독 (kaflix pump) 폐기.
    # 사내 동료 메시지는 우리 backend SSE 가 reporter_task / sse_task 흐름과 동일 경로로 도달.
    # 임베드 VSCode (code-server) — 대시보드의 사이드 패널이 비활성된 상태라 spawn 도 보류.
    # 30082 포트 + brew install 단계 비용 절감. 복원하려면 아래 한 줄 주석만 해제.
    # app["code_server_proc"] = await start_code_server()


async def _stop_background_tasks(app: web.Application) -> None:
    for key in ("reporter_task", "sse_task", "bot_adapter_monitor_task"):
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


# 봇 어댑터 자가치유 — 30s 주기로 죽은 process 검출 + sse_consumer fallback 복구.
_BOT_ADAPTER_MONITOR_INTERVAL_SEC = 30.0


async def _bot_adapter_monitor_loop() -> None:
    from .claude.bootstrap import monitor_bot_adapters
    while True:
        try:
            dead = monitor_bot_adapters()
            if dead:
                log.info("bot-adapter monitor: cleaned %d dead process(es)", dead)
        except Exception:  # noqa: BLE001 — background loop, never fatal
            log.exception("bot-adapter monitor: tick failed")
        await asyncio.sleep(_BOT_ADAPTER_MONITOR_INTERVAL_SEC)


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
    app.router.add_post("/api/setup", setup_handler)
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
