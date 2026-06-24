"""Windows helper — 웹 터미널(ConPTY) 전용 (크로스플랫폼).

[배경]
dev 의 helper 는 웹 터미널만 사용한다(외부 Terminal.app/iTerm 열기는 비활성).
웹 터미널 = 브라우저 xterm.js ↔ aiohttp WebSocket(/ws/terminal) ↔ pty(claude).
macOS/Linux 는 Unix pty + zellij 를 쓰지만 Windows 엔 둘 다 없다. 이 helper 는:
  - Unix pty            → ConPTY (pywinpty)
  - zellij 멀티플렉서   → 불필요 (claude 를 ConPTY 에 직접 실행, helper 가 세션 생명주기 소유)
  - zellij send-keys 주입 → ConPTY 에 직접 write

제공 기능:
  - GET  /api/health
  - WS   /ws/terminal?cwd&cols&rows&agentId&tmuxSession   : 웹 터미널 (claude 호스팅)
  - reporter loop → POST {BE}/api/desktop/local-info       : 살아있는 세션 신고(presence)
  - SSE consumer  → message.deliver 수신 시 해당 세션 ConPTY 에 주입(last-mile)

실행:  cd desktop-agent && uv run python win_helper.py
환경변수: AIDESK_BACKEND_URL(기본 http://localhost:30081), AIDESK_HELPER_PORT(30083),
          AIDESK_REPORT_INTERVAL_SEC(30)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import socket
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx
from aiohttp import WSMsgType, web
from httpx_sse import aconnect_sse
from winpty import PtyProcess

BACKEND = os.environ.get("AIDESK_BACKEND_URL", "http://localhost:30081").rstrip("/")
PORT = int(os.environ.get("AIDESK_HELPER_PORT", "30083"))
INTERVAL = float(os.environ.get("AIDESK_REPORT_INTERVAL_SEC", "30"))
RING_MAX = 256 * 1024  # 재접속 시 화면 복원용 최근 출력 버퍼(세션당)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s win-helper %(message)s")
log = logging.getLogger("win-helper")

# --- aidesk-channel MCP 자동 등록 (macOS bootstrap._register_local_mcp 의 Windows 판) ---
CLAUDE_JSON = Path(os.path.expanduser("~/.claude.json"))


def _resource_base() -> Path:
    """번들 리소스(adesk-cli / aidesk-channel) 루트.

    - frozen(PyInstaller .exe): 실행파일 폴더 (installer 가 리소스를 옆에 동봉).
    - dev: repo 루트 (win_helper.py 는 desktop-agent/ 에 있고 형제로 adesk-cli·aidesk-channel).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


MCP_SERVER_JS = str(_resource_base() / "aidesk-channel" / "src" / "server.js")
NODE_BIN = shutil.which("node") or "node"


def register_local_mcp(workspace_dir: str, agent_id: str) -> None:
    """~/.claude.json 의 projects[ws].mcpServers['aidesk-channel'] 등록 — 터미널 오픈 시 자동 호출.

    macOS 는 bun 바이너리, Windows 는 node + server.js. claude 가 이 워크스페이스에서 뜨면
    aidesk-channel 도구(send_to/reply/check_inbox/list_agents)를 로드해 자동 통신 가능.
    """
    if not agent_id or not workspace_dir:
        return
    try:
        data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8")) if CLAUDE_JSON.exists() else {}
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    legacy = data.get("mcpServers")
    if isinstance(legacy, dict):
        legacy.pop("aidesk-channel", None)  # legacy 글로벌 제거 (macOS 동일)
    projects = data.setdefault("projects", {})
    proj = projects.setdefault(workspace_dir, {})
    if not isinstance(proj, dict):
        proj = projects[workspace_dir] = {}
    servers = proj.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = proj["mcpServers"] = {}
    servers["aidesk-channel"] = {
        "type": "stdio",
        "command": NODE_BIN,
        "args": [MCP_SERVER_JS],
        "env": {
            "AIDESK_AGENT_ID": agent_id,
            "AIDESK_API_URL": BACKEND,
            "AIDESK_HELPER_URL": f"http://localhost:{PORT}",
        },
    }
    proj["hasTrustDialogAccepted"] = True
    try:
        CLAUDE_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log.info("MCP 자동등록 ws=%s agent=%s", workspace_dir, agent_id)
    except Exception as e:  # noqa: BLE001
        log.warning("MCP 등록 실패: %s", e)


class TermSession:
    """세션 1개 = ConPTY(claude) + 출력 버퍼 + 구독자(WS) 큐들. WS 가 끊겨도 살아있음."""

    def __init__(self, name: str, cwd: str, cols: int, rows: int, agent_id: str) -> None:
        self.name = name
        self.loop = asyncio.get_event_loop()
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        if agent_id:
            env["AIDESK_AGENT_ID"] = agent_id
        # cmd 셸을 ConPTY 로 띄우고 곧바로 claude 실행 — claude 종료해도 셸은 남아 재사용/주입 가능.
        self.pty = PtyProcess.spawn(["cmd.exe", "/q"], cwd=cwd or None, env=env, dimensions=(rows, cols))
        if hasattr(self.pty, "encoding"):
            self.pty.encoding = "utf-8"  # write 를 UTF-8 바이트로 (한글 주입)
        # 콘솔 코드페이지를 UTF-8(65001) 로 전환 — cp949 콘솔에서 한글 메시지 주입이
        # 깨지는 문제 방지. claude 실행 *전에* 설정해야 claude 가 UTF-8 stdin 으로 읽음.
        self.pty.write("chcp 65001 >nul\r")
        # 워크스페이스로 cd. **claude 자동실행 안 함** — 첫 오픈은 일반 셸 (기존 web_pty.py 동작과 동일).
        # MCP 가 등록돼 있어, 사용자가 직접 `claude` 실행 시 aidesk-channel 도구가 로드됨.
        if cwd:
            self.pty.write(f'cd /d "{cwd}"\r')
        self.ring: deque[bytes] = deque()
        self.ring_size = 0
        self.subscribers: set[asyncio.Queue[bytes]] = set()
        self._alive = True
        threading.Thread(target=self._reader, name=f"pty-{name}", daemon=True).start()
        log.info("session spawned: %s cwd=%s %dx%d agent=%s", name, cwd, cols, rows, agent_id or "-")

    def _reader(self) -> None:
        """ConPTY 출력을 동기 read → 버퍼 적재 + 모든 구독자 큐에 threadsafe push."""
        while self._alive:
            try:
                data = self.pty.read(4096)
            except EOFError:
                break
            except Exception:  # noqa: BLE001
                break
            if not data:
                if not self.pty.isalive():
                    break
                time.sleep(0.02)
                continue
            b = data.encode("utf-8", "replace")
            self.ring.append(b)
            self.ring_size += len(b)
            while self.ring_size > RING_MAX and len(self.ring) > 1:
                self.ring_size -= len(self.ring.popleft())
            for q in list(self.subscribers):
                self.loop.call_soon_threadsafe(q.put_nowait, b)
        self._alive = False
        log.info("session pty exited: %s", self.name)

    def snapshot(self) -> bytes:
        return b"".join(self.ring)

    def write(self, data: str) -> None:
        try:
            self.pty.write(data)
        except Exception as e:  # noqa: BLE001
            log.warning("pty write failed (%s): %s", self.name, e)

    def resize(self, cols: int, rows: int) -> None:
        try:
            self.pty.setwinsize(rows, cols)
        except Exception:  # noqa: BLE001
            pass

    def alive(self) -> bool:
        return self._alive and self.pty.isalive()


SESSIONS: dict[str, TermSession] = {}


async def health(_r: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok", "service": "aidesk-helper-win", "platform": platform.system(),
        "host": socket.gethostname(), "sessions": sorted(SESSIONS.keys()),
        "backend": "conpty-web-terminal",
    })


async def ws_terminal(request: web.Request) -> web.StreamResponse:
    """브라우저 xterm.js ↔ ConPTY. 입력/출력=binary, resize=TEXT JSON {type:resize,cols,rows}."""
    ws = web.WebSocketResponse(heartbeat=None, max_msg_size=4 * 1024 * 1024)
    await ws.prepare(request)

    cwd = request.query.get("cwd", "").strip()
    if not cwd or not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")  # 존재하지 않는 workspace_dir → 홈으로 폴백 (macOS 핸들러 동일)
    try:
        cols = max(20, min(500, int(request.query.get("cols", "80"))))
    except ValueError:
        cols = 80
    try:
        rows = max(5, min(200, int(request.query.get("rows", "24"))))
    except ValueError:
        rows = 24
    agent_id = request.query.get("agentId", "").strip()
    name = request.query.get("tmuxSession", "").strip() or (f"win-{agent_id[:8]}" if agent_id else "win-default")

    # 터미널 오픈 시 aidesk-channel MCP 자동 등록 (기존 macOS web_terminal_handler 와 동일).
    register_local_mcp(cwd, agent_id)

    sess = SESSIONS.get(name)
    if sess is None or not sess.alive():
        sess = TermSession(name, cwd, cols, rows, agent_id)
        SESSIONS[name] = sess
    else:
        sess.resize(cols, rows)
        log.info("ws-terminal: re-attach %s", name)

    q: asyncio.Queue[bytes] = asyncio.Queue()
    sess.subscribers.add(q)
    snap = sess.snapshot()
    if snap:
        await ws.send_bytes(snap)  # 재접속 화면 복원

    async def pump_out() -> None:
        while True:
            b = await q.get()
            await ws.send_bytes(b)

    out_task = asyncio.create_task(pump_out())
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                sess.write(msg.data.decode("utf-8", "replace"))
            elif msg.type == WSMsgType.TEXT:
                try:
                    obj = json.loads(msg.data)
                    if obj.get("type") == "resize":
                        sess.resize(int(obj["cols"]), int(obj["rows"]))
                except Exception:  # noqa: BLE001
                    sess.write(msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break
    finally:
        out_task.cancel()
        sess.subscribers.discard(q)  # pty 는 살려둠 → 재접속 가능
        log.info("ws-terminal: detach %s (pty alive=%s)", name, sess.alive())
    return ws


async def reporter_loop() -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            sessions = [{"name": n, "attached": bool(s.subscribers)} for n, s in SESSIONS.items() if s.alive()]
            try:
                workspaces = await asyncio.to_thread(scan_workspaces)
            except Exception as e:  # noqa: BLE001
                log.warning("scan_workspaces 실패: %s", e)
                workspaces = []
            payload = {"workspaces": workspaces, "tmuxSessions": sessions}
            try:
                r = await client.post(f"{BACKEND}/api/desktop/local-info", json=payload)
                log.info("reporter → %s (ws=%d sessions=%d)", r.status_code, len(workspaces), len(sessions))
            except Exception as e:  # noqa: BLE001
                log.warning("reporter failed: %s", e)
            await asyncio.sleep(INTERVAL)


async def sse_loop() -> None:
    """message.deliver → 해당 tmuxSession 의 ConPTY 에 메시지 주입(last-mile)."""
    url = f"{BACKEND}/api/desktop/events"
    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            try:
                async with aconnect_sse(client, "GET", url) as es:
                    log.info("SSE connected → %s", url)
                    async for sse in es.aiter_sse():
                        if sse.event != "message.deliver":
                            continue
                        try:
                            d = json.loads(sse.data)
                        except Exception:  # noqa: BLE001
                            continue
                        target = (d.get("toTmuxSession") or "").strip()
                        sess = SESSIONS.get(target)
                        rendered = f"[from {d.get('fromAgentName','?')}] {d.get('content','')}"
                        log.info("SSE recv repr=%r", rendered)  # 진단: SSE 수신 한글 깨짐 확인용
                        if sess and sess.alive():
                            sess.write(rendered)
                            await asyncio.sleep(0.25)  # paste-detect 회피 후 Enter 분리 전송
                            sess.write("\r")
                            log.info("주입 OK → session=%s msg=%s", target, d.get("messageId"))
                        else:
                            log.info("주입 skip — 세션 없음(target=%s). 활성: %s", target, sorted(SESSIONS))
            except Exception as e:  # noqa: BLE001
                log.warning("SSE 끊김 (%s) — 5초 후 재연결", e)
                await asyncio.sleep(5.0)


@web.middleware
async def cors_mw(request: web.Request, handler):
    """브라우저(30080)에서 helper 로 오는 cross-origin fetch 허용 + OPTIONS preflight."""
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    try:  # WS(prepare됨) 응답엔 헤더 추가 불가 → 무시
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    except Exception:  # noqa: BLE001
        pass
    return resp


async def browse_workspace(_request: web.Request) -> web.Response:
    """대시보드 '찾아보기' → Windows 폴더 선택창 (osascript 대체). {rc, path} 반환 (취소=빈 path)."""
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
        '$f.Description = "AI Desk 워크스페이스 폴더 선택";'
        "$f.ShowNewFolderButton = $true;"
        "$top = New-Object System.Windows.Forms.Form; $top.TopMost = $true;"
        "if ($f.ShowDialog($top) -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ [Console]::Out.Write($f.SelectedPath) }"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-STA", "-NoProfile", "-Command", ps,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        path = out.decode("utf-8", "replace").strip().replace("\\", "/")
        log.info("browse-workspace → %r", path)
        return web.json_response({"rc": 0, "path": path})
    except Exception as e:  # noqa: BLE001
        return web.json_response({"rc": 1, "message": f"폴더 선택 실패: {e}"})


# --- Claude 사용량 statusLine (macOS claude/usage.py 의 Windows 판) ---
USAGE_DIR = Path(os.path.expanduser("~/.claude/aidesk-usage"))
SETTINGS_PATH = Path(os.path.expanduser("~/.claude/settings.json"))
STATUSLINE_SCRIPT = _resource_base() / "adesk-cli" / "bin" / "aidesk-statusline.cjs"
_SCRIPT_BASE = "aidesk-statusline"

# --- 워크스페이스 스캔 (macOS claude/scanner.scan_workspaces 의 Windows 판) ---
# reporter 가 워크스페이스별 contextPct 를 backend 로 보내 → AgentCard 에 컨텍스트 바 표시.
CLAUDE_PROJECTS_ROOT = Path(os.path.expanduser("~/.claude/projects"))
_ACTIVE_WINDOW_SEC = 120


def _load_cwd_to_context_pct() -> dict:
    """~/.claude/aidesk-usage/*.json → {cwd(정규화): context_pct}. 같은 cwd 는 최신 mtime."""
    if not USAGE_DIR.is_dir():
        return {}
    acc: dict = {}  # cwd -> (mtime, ctx)
    for p in USAGE_DIR.iterdir():
        if not p.is_file() or p.suffix != ".json":
            continue
        try:
            mtime = p.stat().st_mtime
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cwd = rec.get("cwd")
        rem = rec.get("contextRemainingPct")
        if not cwd or rem is None:
            continue
        cwd = str(cwd).replace("\\", "/")  # Windows backslash → forward (agent workspace_dir 매칭)
        try:
            ctx = max(0, min(100, 100 - int(rem)))
        except (TypeError, ValueError):
            continue
        prev = acc.get(cwd)
        if prev is None or mtime > prev[0]:
            acc[cwd] = (mtime, ctx)
    return {c: v[1] for c, v in acc.items()}


def _extract_cwd(jsonl_path: Path) -> str | None:
    """jsonl 앞쪽 줄에서 cwd 추출 → forward-slash 정규화."""
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fp:
            for idx, line in enumerate(fp):
                if idx >= 40:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("cwd"), str):
                    return obj["cwd"].replace("\\", "/")
    except OSError:
        return None
    return None


def _find_latest_jsonl(project_dir: Path) -> Path | None:
    latest = None
    latest_mtime = -1.0
    for root, _dirs, files in os.walk(project_dir):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            p = Path(root) / name
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > latest_mtime:
                latest_mtime = m
                latest = p
    return latest


def scan_workspaces() -> list[dict]:
    """~/.claude/projects/ + aidesk-usage 스캔 → 워크스페이스별 {workspaceDir, status, contextPct, ...}."""
    cwd_ctx = _load_cwd_to_context_pct()
    now = time.time()
    out: list[dict] = []
    seen: set[str] = set()
    if CLAUDE_PROJECTS_ROOT.is_dir():
        for entry in sorted(CLAUDE_PROJECTS_ROOT.iterdir()):
            if not entry.is_dir():
                continue
            latest = _find_latest_jsonl(entry)
            if latest is None:
                continue  # 세션 jsonl 없음 → cwd 불명 (아래 usage cwd 보강에서 커버)
            try:
                mtime = latest.stat().st_mtime
            except OSError:
                continue
            cwd = _extract_cwd(latest)
            if not cwd:
                continue
            age = int(now - mtime)
            out.append({
                "encodedDir": entry.name,
                "workspaceDir": cwd,
                "latestJsonl": str(latest),
                "latestMtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "ageSec": age,
                "status": "active" if age <= _ACTIVE_WINDOW_SEC else "idle",
                "contextPct": cwd_ctx.get(cwd),
            })
            seen.add(cwd)
    # jsonl 은 아직 없지만 aidesk-usage 에는 있는 cwd (claude 부팅 직후) — 컨텍스트 즉시 표시용.
    # Windows claude 는 대화 전까지 jsonl 을 안 써서, usage 파일(부팅 시 기록)만으로도 보고.
    for cwd, ctx in cwd_ctx.items():
        if cwd in seen:
            continue
        out.append({
            "encodedDir": "",
            "workspaceDir": cwd,
            "latestJsonl": None,
            "latestMtime": None,
            "ageSec": 0,
            "status": "active",
            "contextPct": ctx,
        })
    return out


def _read_settings() -> dict | None:
    try:
        if not SETTINGS_PATH.exists() or SETTINGS_PATH.stat().st_size == 0:
            return None
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _inspect_hook() -> str:
    root = _read_settings()
    if not root:
        return "absent"
    sl = root.get("statusLine")
    if not isinstance(sl, dict):
        return "absent"
    cmd = str(sl.get("command") or "").strip()
    if not cmd:
        return "absent"
    return "ours" if _SCRIPT_BASE in cmd else "other"


def install_statusline_hook() -> int:
    """settings.json 에 statusLine 주입. 0=ok, 1=스크립트 없음, 2=쓰기 실패."""
    if not STATUSLINE_SCRIPT.is_file():
        return 1
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        root = _read_settings() or {}
        root["statusLine"] = {"type": "command", "command": f'"{NODE_BIN}" "{STATUSLINE_SCRIPT}"'}
        SETTINGS_PATH.write_text(json.dumps(root, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("usage: statusLine 설치 → %s", STATUSLINE_SCRIPT)
        return 0
    except OSError as e:
        log.warning("usage: statusLine 설치 실패: %s", e)
        return 2


def auto_install_statusline() -> None:
    """helper 시작 시 1회 — 다른 statusLine 점유 중이면 보류 (macOS auto_install_on_startup 동등)."""
    s = _inspect_hook()
    if s == "other":
        log.info("usage: statusLine 다른 명령 점유 — 자동설치 보류")
        return
    if s == "ours":
        return
    install_statusline_hook()


def _usage_num(node, default, integer=False):
    try:
        return int(node) if integer else int(round(float(node)))
    except (TypeError, ValueError):
        return default


def get_local_usage() -> dict:
    hook = _inspect_hook()
    rs = {
        "fiveHourPct": -1, "fiveHourResetsAt": 0, "weeklyPct": -1, "weeklyResetsAt": 0,
        "contextPct": -1, "source": "", "ready": False,
        "hookInstalled": hook == "ours", "hookOccupiedByOther": hook == "other",
    }
    if not USAGE_DIR.is_dir():
        return rs
    now = int(time.time())
    cands = []
    try:
        for p in USAGE_DIR.iterdir():
            if p.is_file() and p.name.endswith(".json"):
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                    if int(d.get("fiveHourResetsAt") or 0) > now:
                        cands.append(p)
                except Exception:  # noqa: BLE001
                    pass
    except OSError:
        return rs
    if not cands:
        return rs
    latest = max(cands, key=lambda p: p.stat().st_mtime)
    try:
        d = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return rs
    rs["ready"] = True
    rs["source"] = str(latest)
    rs["fiveHourPct"] = _usage_num(d.get("fiveHourUsedPct"), -1)
    rs["fiveHourResetsAt"] = _usage_num(d.get("fiveHourResetsAt"), 0, integer=True)
    rs["weeklyPct"] = _usage_num(d.get("weeklyUsedPct"), -1)
    rs["weeklyResetsAt"] = _usage_num(d.get("weeklyResetsAt"), 0, integer=True)
    rem = _usage_num(d.get("contextRemainingPct"), -1)
    if rem >= 0:
        rs["contextPct"] = max(0, min(100, 100 - rem))
    return rs


async def usage_local(_request: web.Request) -> web.Response:
    return web.json_response(get_local_usage())


async def usage_install_statusline(_request: web.Request) -> web.Response:
    rc = install_statusline_hook()
    if rc == 0:
        return web.json_response({"rc": 0, "message": "ok"})
    msg = ("statusline 스크립트(adesk-cli/bin/aidesk-statusline.cjs)를 찾지 못했습니다."
           if rc == 1 else "~/.claude/settings.json 갱신 실패.")
    return web.json_response({"rc": rc, "message": msg}, status=500)


async def main() -> None:
    auto_install_statusline()  # 시작 시 statusLine 자동 등록 (macOS auto_install_on_startup 동등)
    app = web.Application(middlewares=[cors_mw])
    app.router.add_get("/api/health", health)
    app.router.add_get("/ws/terminal", ws_terminal)
    app.router.add_post("/api/browse-workspace", browse_workspace)
    app.router.add_get("/api/usage/local", usage_local)
    app.router.add_post("/api/usage/install-statusline", usage_install_statusline)
    runner = web.AppRunner(app)
    await runner.setup()
    # 웹터미널(dev)=30084, 대시보드 $helper(browse/version)=30083 → 둘 다 리슨.
    ports = sorted({PORT, 30083})
    listening = []
    for p in ports:
        try:
            await web.TCPSite(runner, "127.0.0.1", p).start()
            listening.append(p)
        except OSError as e:
            log.warning("port %d bind 실패: %s", p, e)
    log.info("win-helper(ConPTY) up → ports=%s backend=%s", listening, BACKEND)
    await asyncio.gather(reporter_loop(), sse_loop())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
