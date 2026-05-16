"""xterm.js ↔ 로컬 PTY 양방향 WebSocket 펌프.

백엔드 TerminalWebSocketHandler 와 동일한 프로토콜:
  - 클라이언트 → 서버: 일반 텍스트 = stdin 입력. JSON `{"type":"resize","cols":N,"rows":N}` = PTY 리사이즈.
  - 서버 → 클라이언트: PTY stdout 의 raw 바이트를 UTF-8 텍스트로 전달.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import pty
import re
import struct
import subprocess
import termios
from pathlib import Path

from aiohttp import WSMsgType, web

from .os_bridge import _has_past_session

log = logging.getLogger(__name__)

_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_READ_BUFFER = 4096
_DEFAULT_COLS = 120
_DEFAULT_ROWS = 30


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _build_command(session: str, workspace_dir: str | None, model: str | None) -> list[str]:
    """`tmux new-session -A -s {session} [<cli>]` 형태로 argv 구성.

    cli 가 None 이면 셸만 띄움. 등록된 에이전트 모델에 따라 claude / codex / hermes 자동 선택.
    """
    base = ["tmux", "new-session", "-A", "-s", session]
    cli = _resolve_cli_command(workspace_dir, model)
    if cli:
        # tmux 의 command 인자는 단일 문자열로 (예: "claude -c") 전달.
        # argv 를 쪼개면 `-c` 가 tmux 옵션으로 오해됨.
        base.append(cli)
    return base


def _resolve_cli_command(workspace_dir: str | None, model: str | None) -> str | None:
    if model is None or not model.strip():
        return _claude_with_resume(workspace_dir)
    m = model.strip().lower()
    if m.startswith("claude"):
        return _claude_with_resume(workspace_dir)
    if m == "codex":
        return "codex"
    if m == "hermes":
        return "hermes"
    log.warning("unknown model '%s' — falling back to claude", model)
    return _claude_with_resume(workspace_dir)


def _claude_with_resume(workspace_dir: str | None) -> str:
    if workspace_dir and _has_past_session(workspace_dir):
        return "claude -c"
    return "claude"


async def _pump_pty_to_ws(ws: web.WebSocketResponse, master_fd: int) -> None:
    """PTY stdout → WS 텍스트. run_in_executor 로 blocking read 를 풀어 단순화."""
    loop = asyncio.get_event_loop()
    while not ws.closed:
        try:
            data = await loop.run_in_executor(None, os.read, master_fd, _READ_BUFFER)
        except OSError:
            break
        if not data:
            break
        try:
            await ws.send_str(data.decode("utf-8", errors="replace"))
        except ConnectionResetError:
            break
    if not ws.closed:
        await ws.close()


async def terminal_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(autoping=True)
    await ws.prepare(request)

    session = request.query.get("session", "").strip()
    if not session or not _SESSION_NAME_RE.match(session):
        log.warning("terminal WS rejected: invalid session name %r", session)
        await ws.close(code=4400, message=b"invalid session name")
        return ws

    workspace_dir = request.query.get("workspaceDir") or None
    if workspace_dir and not Path(workspace_dir).is_dir():
        workspace_dir = None
    model = request.query.get("model") or None

    cmd = _build_command(session, workspace_dir, model)
    master_fd, slave_fd = pty.openpty()
    # LaunchAgent 로 실행될 땐 부모 env 에 TERM 이 없거나 `dumb` 이라 claude 가
    # "terminal does not support clear" 무한 출력. xterm.js 가 실제로 지원하는
    # capability 로 명시 — 외부 Terminal.app 동작과 동일하게 맞춤.
    # LANG 누락 시 한글 wide-char 처리 실패 → 임베디드 터미널이 깨짐. plist 가
    # LANG 박지 못한 환경(예: 옛 .pkg) 에서도 폴백으로 ko_KR.UTF-8 또는 en_US.UTF-8 보장.
    pty_env = {
        **os.environ,
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
        "LANG": os.environ.get("LANG") or "en_US.UTF-8",
        "LC_CTYPE": os.environ.get("LC_CTYPE") or "UTF-8",
    }
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=workspace_dir,
            env=pty_env,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as e:
        os.close(master_fd)
        os.close(slave_fd)
        log.warning("terminal WS PTY spawn failed: session=%s err=%s", session, e)
        await ws.close(code=4500, message=b"pty spawn failed")
        return ws
    os.close(slave_fd)
    _set_winsize(master_fd, _DEFAULT_ROWS, _DEFAULT_COLS)

    log.info("terminal WS open: session=%s pid=%s ws=%s", session, proc.pid, id(ws))

    pump_task = asyncio.create_task(_pump_pty_to_ws(ws, master_fd))
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            payload = msg.data
            # 제어 메시지 (JSON) vs raw 입력 — 백엔드와 동일한 핫패스 분기.
            if payload and payload[0] == "{":
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    obj = None
                if isinstance(obj, dict):
                    mtype = obj.get("type")
                    if mtype == "resize":
                        cols = int(obj.get("cols") or _DEFAULT_COLS)
                        rows = int(obj.get("rows") or _DEFAULT_ROWS)
                        try:
                            _set_winsize(master_fd, rows, cols)
                        except OSError:
                            pass
                        continue
                    if mtype == "input":
                        os.write(master_fd, str(obj.get("data") or "").encode("utf-8"))
                        continue
                    log.debug("terminal WS unknown control: %s", mtype)
                    continue
            try:
                os.write(master_fd, payload.encode("utf-8"))
            except OSError:
                break
    finally:
        log.info("terminal WS close: session=%s ws=%s", session, id(ws))
        pump_task.cancel()
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
    return ws
