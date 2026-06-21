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
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=4 * 1024 * 1024)
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

    log.info(
        "ws-terminal: open client=%s cwd=%s cols=%d rows=%d shell=%s agentId=%s",
        request.remote, cwd, cols, rows, shell, agent_id or "-",
    )

    # spawn 전 ~/.claude.json 의 mcp 등록 갱신 — 옛 'node + script' patterns 가 남아있으면
    # 새 binary 직접 실행으로 자동 마이그. 0.8.15 까지는 사용자가 수동 fix 필요했음.
    if agent_id and cwd_q:
        try:
            from ..claude.bootstrap import _register_local_mcp  # noqa: PLC0415
            _register_local_mcp(cwd_q, agent_id)
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
    # asyncio.create_task 를 그냥 호출하면 event loop 의 weak reference 정책상 task 가 GC
    # 될 수 있음 (Python 3.11+). 강한 reference 유지 + done callback discard.
    pending_tasks: set[asyncio.Task] = set()

    def _spawn(coro) -> None:
        task = asyncio.create_task(coro)
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

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
            _spawn(ws.close())
            return
        _spawn(ws.send_bytes(data))

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
        # SIGHUP → 짧게 대기 → 그래도 살아있으면 SIGKILL — zombie 방지.
        # WNOHANG 만으로는 SIGHUP 무시 shell (예: trap) 시 child 가 reaped 안 됨.
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError:
            pass
        reaped = False
        for _ in range(10):  # 약 1초까지 polling (100ms * 10).
            try:
                rc_pid, _status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                reaped = True
                break
            if rc_pid != 0:
                reaped = True
                break
            await asyncio.sleep(0.1)
        if not reaped:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.waitpid(pid, 0)  # blocking — SIGKILL 후엔 즉시 reaped.
            except ChildProcessError:
                pass
        # 안전하게 남은 task 들도 정리 (ws.close / send_bytes 의 race 회피).
        for t in list(pending_tasks):
            if not t.done():
                t.cancel()
        log.info("ws-terminal: close client=%s pid=%d", request.remote, pid)

    return ws
