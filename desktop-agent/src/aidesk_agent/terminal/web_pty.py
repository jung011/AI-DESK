"""웹 터미널용 PTY WebSocket handler.

브라우저(xterm.js) ↔ aiohttp WebSocket ↔ pty subprocess (zsh) 의 bidirectional
binary bridge. agent 별 workspaceDir 로 새 shell 시작.

옛 pty_bridge 의 한글 깨짐 / 격자 좁아짐 이슈는:
- env LANG=ko_KR.UTF-8 / LC_ALL=ko_KR.UTF-8 명시 → 한글
- WebSocket binary frame (BYTES) + xterm.write(Uint8Array) → encoding mismatch 회피
- {"type":"resize","cols","rows"} control TEXT message + TIOCSWINSZ → cols 정확
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import pty
import shutil
import signal
import struct
import termios

from aiohttp import web

log = logging.getLogger(__name__)

# 최대 read 단위 — claude code 같은 TUI 가 큰 ANSI 출력 보낼 때 chunk 잘게 자르지 않음.
_READ_CHUNK = 8192
# default shell — zsh 우선, 없으면 bash.
_DEFAULT_SHELL_CANDIDATES = ("/bin/zsh", "/usr/bin/zsh", "/bin/bash", "/usr/bin/bash")


def _pick_shell() -> str:
    for s in _DEFAULT_SHELL_CANDIDATES:
        if os.path.exists(s):
            return s
    return shutil.which("zsh") or shutil.which("bash") or "/bin/sh"


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    """TIOCSWINSZ — xterm.js fit-addon 의 cols/rows 를 pty 에 즉시 반영."""
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


async def web_terminal_handler(request: web.Request) -> web.StreamResponse:
    """`ws://127.0.0.1:30083/ws/terminal?cwd=...&cols=...&rows=...&shell=...`.

    - agent 별 cwd 로 shell spawn. cwd 없으면 $HOME.
    - 입력 = binary frame (Uint8Array) → os.write(fd).
    - 출력 = pty read → ws.send_bytes (binary frame).
    - resize = TEXT frame JSON {type:'resize', cols, rows} → TIOCSWINSZ.
    """
    # heartbeat=30 시 browser tab background 의 setTimeout throttle 로 pong 지연 → aiohttp abort
    # → code 1006 끊김. claude code TUI 같이 사용자 focus 잃기 쉬운 환경에서 빈번. None = aiohttp
    # 가 application-level ping 안 보냄 → browser 가 keepalive 책임. pty 출력 자체가 traffic.
    ws = web.WebSocketResponse(heartbeat=None, max_msg_size=4 * 1024 * 1024)
    await ws.prepare(request)

    cwd_q = request.query.get("cwd", "").strip()
    cwd = cwd_q if cwd_q and os.path.isdir(cwd_q) else os.path.expanduser("~")
    try:
        cols = max(20, min(500, int(request.query.get("cols", "80"))))
    except ValueError:
        cols = 80
    try:
        rows = max(5, min(200, int(request.query.get("rows", "24"))))
    except ValueError:
        rows = 24
    shell_q = request.query.get("shell", "").strip()
    shell = shell_q if shell_q and os.path.exists(shell_q) else _pick_shell()
    # agentId — claude 의 aidesk-channel mcp 가 *어떤 agent 로* 메시지 보낼지 결정.
    # AIDESK_AGENT_ID env 가 helper-spawned shell 에 있어야 mcp 가 정상 작동
    # (memory: workspace-local mcp 패턴, AIDESK_AGENT_ID env 명시).
    agent_id = request.query.get("agentId", "").strip()
    # api_url override — dev 전용. frontend 가 명시하면 *이 workspace 의 mcp env* 의
    # AIDESK_API_URL 을 이 값으로. 명시 안 하면 helper plist 의 AIDESK_HUB_URL (prod).
    api_url_q = request.query.get("apiUrl", "").strip()

    log.info(
        "ws-terminal: open client=%s cwd=%s cols=%d rows=%d shell=%s agentId=%s apiUrl=%s",
        request.remote, cwd, cols, rows, shell, agent_id or "-", api_url_q or "-",
    )

    # spawn 전 ~/.claude.json 의 mcp 등록 갱신 — 옛 'node + script' patterns 가 남아있으면
    # 새 binary 직접 실행으로 자동 마이그. 0.8.15 까지는 사용자가 수동 fix 필요했음.
    if agent_id and cwd_q:
        try:
            from ..claude.bootstrap import _register_local_mcp  # noqa: PLC0415
            # dev helper (port 30084) 인지 추론 — 기본 30083 이면 None (prod). 30083 외엔
            # mcp 가 *이 helper* 조회하도록 AIDESK_HELPER_URL 명시.
            try:
                helper_port_self = request.transport.get_extra_info("sockname")[1]
            except Exception:  # noqa: BLE001
                helper_port_self = None
            helper_url_override = (
                f"http://127.0.0.1:{helper_port_self}"
                if helper_port_self and helper_port_self != 30083
                else None
            )
            _register_local_mcp(
                cwd_q, agent_id,
                api_url=api_url_q or None,
                helper_url=helper_url_override,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("ws-terminal: mcp re-register failed cwd=%s agent=%s err=%s", cwd_q, agent_id, e)

    pid, fd = pty.fork()
    if pid == 0:
        # child process — exec shell. 이 분기는 절대 return 안 함.
        env = os.environ.copy()
        env["LANG"] = "ko_KR.UTF-8"
        env["LC_ALL"] = "ko_KR.UTF-8"
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        if agent_id:
            # claude code 가 spawn 한 mcp server 들에 propagate 되어
            # aidesk-channel mcp 가 어떤 agent 로 메시지 보낼지 결정.
            env["AIDESK_AGENT_ID"] = agent_id
        # 사용자 셸 prompt 가 cwd 잡도록 디렉토리 이동.
        try:
            os.chdir(cwd)
        except OSError:
            pass
        try:
            os.execvpe(shell, [shell, "-il"], env)
        except OSError as e:
            print(f"[aidesk-web-pty] exec failed: {e}", flush=True)
            os._exit(127)

    # parent
    _set_winsize(fd, rows, cols)

    loop = asyncio.get_event_loop()
    closed = asyncio.Event()

    def _on_pty_readable() -> None:
        if closed.is_set():
            return
        try:
            data = os.read(fd, _READ_CHUNK)
        except OSError:
            data = b""
        if not data:
            closed.set()
            try:
                loop.remove_reader(fd)
            except (OSError, ValueError):
                pass
            asyncio.create_task(ws.close())
            return
        asyncio.create_task(ws.send_bytes(data))

    loop.add_reader(fd, _on_pty_readable)

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.BINARY:
                try:
                    os.write(fd, msg.data)
                except OSError:
                    break
            elif msg.type == web.WSMsgType.TEXT:
                # control — 현재는 resize 만. JSON 파싱 실패는 무시.
                try:
                    j = json.loads(msg.data)
                except (TypeError, ValueError):
                    continue
                if j.get("type") == "resize":
                    try:
                        c = int(j.get("cols", 80))
                        r = int(j.get("rows", 24))
                        _set_winsize(fd, r, c)
                    except (TypeError, ValueError):
                        pass
                elif j.get("type") == "ping":
                    # heartbeat — aiohttp heartbeat 와 별개로 client-side ping.
                    await ws.send_str(json.dumps({"type": "pong"}))
            elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.ERROR):
                break
    finally:
        closed.set()
        try:
            loop.remove_reader(fd)
        except (OSError, ValueError):
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError:
            pass
        # zombie 회수.
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        log.info("ws-terminal: close client=%s pid=%d", request.remote, pid)

    return ws
