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
import subprocess
import termios

from aiohttp import web

import time as _time


def _poll_and_inject_identity(tmux_session: str, agent_name: str) -> None:
    """옵션 C — 사용자가 직접 `claude` 명령 + Enter 후, claude TUI prompt ready 시점에
    *identity prompt 자동 inject*.

    polling — capture-pane 으로 *Channels confirmation dialog* 또는 *claude TUI
    footer (← for agents)* 검출. 5분 안 ready 안 되면 abort (사용자가 claude 안 띄움).

    Channels confirmation 가 *시작 시 1회* 자동으로 Enter 처리 — 사용자 손 0.
    """
    from ..claude.bootstrap import _build_identity_prompt
    deadline = _time.monotonic() + 300  # 5분 limit
    identity_prompt = _build_identity_prompt(agent_name)
    confirmed_channels = False
    while _time.monotonic() < deadline:
        _time.sleep(2.0)
        # session alive 검사
        check = subprocess.run(
            ["tmux", "has-session", "-t", tmux_session],
            capture_output=True,
        )
        if check.returncode != 0:
            log.info("ws-terminal: identity poll — session gone, abort %s", tmux_session)
            return
        try:
            cap = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", tmux_session],
                capture_output=True, text=True, timeout=2,
            )
            screen = cap.stdout or ""
        except (subprocess.TimeoutExpired, OSError):
            continue
        # 1) Channels confirmation dialog 단계 — 자동 Enter
        if "I am using this for local development" in screen and not confirmed_channels:
            try:
                subprocess.run(
                    ["tmux", "send-keys", "-t", tmux_session, "C-m"],
                    capture_output=True, timeout=2,
                )
                confirmed_channels = True
                log.info("ws-terminal: identity poll — Channels confirmation Enter %s", tmux_session)
            except (subprocess.SubprocessError, OSError):
                pass
            continue
        # 2) claude TUI ready — footer 의 `for agents` 표시 + prompt 영역 빈 상태
        #    (`I am using this for local development` 안 보임 + `for agents` 보임)
        if "for agents" in screen and "I am using this for local development" not in screen:
            # identity prompt inject
            try:
                subprocess.run(
                    ["tmux", "send-keys", "-l", "-t", tmux_session, identity_prompt],
                    check=True, capture_output=True,
                )
                _time.sleep(2.0)
                subprocess.run(
                    ["tmux", "send-keys", "-t", tmux_session, "Enter"],
                    check=True, capture_output=True,
                )
                _time.sleep(0.3)
                subprocess.run(
                    ["tmux", "send-keys", "-t", tmux_session, "C-m"],
                    check=False, capture_output=True,
                )
                log.info("ws-terminal: identity prompt injected agent=%s session=%s", agent_name, tmux_session)
                return
            except subprocess.CalledProcessError as e:
                log.warning("ws-terminal: identity prompt inject retry — %s", e)
                continue
    log.info("ws-terminal: identity poll deadline reached — abort %s", tmux_session)

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
    # tmuxSession — 있으면 tmux attach 패턴 (ws 끊겨도 session + claude 살아있음).
    # 없으면 옛 zsh 직접 spawn (backward compatible).
    tmux_session = request.query.get("tmuxSession", "").strip()
    # agentName — *처음 claude 부팅* 시 identity prompt 자동 inject 용. 옛
    # start_claude_with_mode 의 _build_identity_prompt 부활.
    agent_name = request.query.get("agentName", "").strip()
    # background ws (dashboard mini preview 등) — read-only 라 tmux session 의 *global
    # cols/rows 강제 X* + *history dump skip*. 같은 session 에 *터미널 페이지의 큰 client +
    # mini preview 의 작은 client* 동시 attach 시 *mini 의 작은 cols 가 winner* → 터미널
    # 탭의 큰 viewport 에 작은 cols line + padding (·) 가득 사고 차단. aggressive-resize
    # on 가 client 별 grid 분리하지만 capture-pane / resize-window 는 session global.
    #
    # 자동 분류 = 명시 background=1 query 또는 *작은 cols (< 150)* — 사용자 view (보통
    # 150+ cols) 와 mini preview (100 cols) 자동 구별. frontend code 손 안 대고 cols
    # 만으로 자동 path 분기.
    background_mode = (
        request.query.get("background", "").strip() == "1"
        or cols < 150
    )

    log.info(
        "ws-terminal: open client=%s cwd=%s cols=%d rows=%d shell=%s agentId=%s apiUrl=%s tmux=%s",
        request.remote, cwd, cols, rows, shell, agent_id or "-", api_url_q or "-",
        tmux_session or "-",
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

    # tmux session 존재 검사 + 없으면 detached 모드로 새로 띄움. cwd / env 같이.
    if tmux_session:
        try:
            rc = subprocess.run(
                ["tmux", "has-session", "-t", tmux_session],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
        except FileNotFoundError:
            log.warning("ws-terminal: tmux not found — fallback to direct zsh")
            tmux_session = ""
            rc = 1
        if tmux_session and rc != 0:
            # 새 session 생성 — env-prefix 패턴 ([[feedback-helper-tmux-child-env-injection]]).
            new_env = ["env", f"LANG=ko_KR.UTF-8", f"LC_ALL=ko_KR.UTF-8", f"TERM=xterm-256color", "COLORTERM=truecolor"]
            if agent_id:
                new_env.append(f"AIDESK_AGENT_ID={agent_id}")
            new_cmd = [
                "tmux", "new-session", "-d",
                "-s", tmux_session,
                "-x", str(cols), "-y", str(rows),
                "-c", cwd,
            ]
            # Agent Teams env (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1) 는
            # ~/.claude/settings.json 박혀있어 중복 — 제거. is_dev_macos 는 polling
            # thread schedule 조건으로 keep.
            import sys as _sys  # noqa: PLC0415
            is_dev_macos = os.environ.get("AIDESK_ENV") == "dev" and _sys.platform == "darwin"
            # shell 명령 = zsh -il (옛 동작 — 사용자가 직접 claude 입력). 옵션 C.
            # claude 자동 시작 분기 제거 — 카드 click 시 zsh 만, 사용자가 *햄버거 →
            # 클로드 열기* 로 명령어 textarea 박은 후 직접 Enter.
            shell_cmd = " ".join(new_env) + " " + shell + " -il"
            new_cmd.append(shell_cmd)
            try:
                subprocess.run(new_cmd, check=False)
                # mouse off — xterm.js 가 native scroll 받게. tmux mouse on 이면 scroll
                # 이벤트가 tmux 의 copy mode 로 흡수됨.
                subprocess.run(
                    ["tmux", "set-option", "-t", tmux_session, "mouse", "off"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False,
                )
                # aggressive-resize on — 여러 client (mini preview + 큰 화면) attach 시
                # *현재 active client 의 grid* 만 적용. 작은 grid client 가 큰 client
                # 의 grid 강제 wrap 시키는 사고 차단.
                subprocess.run(
                    ["tmux", "set-window-option", "-t", tmux_session, "aggressive-resize", "on"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False,
                )
                # detach-on-destroy off — 사용자 페이지 reload 시 ws disconnect → SIGHUP →
                # tmux client 끊김. 사용자 mac global tmux 의 detach-on-destroy on 이면
                # 마지막 client 끊긴 시점 *session 자체 종료* → claude 같이 죽음. session
                # 단위 off 박아 사용자 환경 보존 + claude 살림.
                subprocess.run(
                    ["tmux", "set-option", "-t", tmux_session, "detach-on-destroy", "off"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False,
                )
                log.info("ws-terminal: tmux new-session %s @ cwd=%s (mouse off + aggressive-resize on + detach-on-destroy off)", tmux_session, cwd)
                # 옵션 C — identity prompt 자동 inject 는 *background polling* 으로.
                # 사용자가 *햄버거 → 클로드 열기* + Enter 직접 → zsh 가 claude 실행 →
                # Channels confirmation dialog → polling 이 dialog 통과 + claude prompt
                # ready 검출 → identity prompt send-keys + Enter. first_boot agent 만.
                # 옛 is_dev_macos guard 가 prod 의 identity inject 까지 죽이는 사고 fix.
                # _poll_and_inject_identity = tmux capture-pane 기반이라 mac/linux 모두 가능.
                if agent_id and agent_name:
                    try:
                        import threading as _threading
                        from .._shared import has_past_session
                        is_first_boot = not has_past_session(cwd) if cwd else True
                        if is_first_boot:
                            _threading.Thread(
                                target=_poll_and_inject_identity,
                                args=(tmux_session, agent_name),
                                daemon=True,
                            ).start()
                            log.info("ws-terminal: identity prompt poll started agent=%s session=%s", agent_name, tmux_session)
                    except Exception as e:  # noqa: BLE001
                        log.warning("ws-terminal: identity prompt poll failed: %s", e)
            except OSError as e:
                log.warning("ws-terminal: tmux new-session failed err=%s", e)
                tmux_session = ""  # fallback

    # 기존 session attach 든 새 session 이든 detach-on-destroy off 보장 — 사용자 mac
    # global tmux 의 'on' default 가 *마지막 client 끊기면 session 종료* → claude 같이
    # 죽는 사고 차단. 새 session 분기에선 위에서 박았지만 *옛 session attach* case 도
    # 같이 cover. idempotent — 이미 off 면 no-op.
    if tmux_session:
        subprocess.run(
            ["tmux", "set-option", "-t", tmux_session, "detach-on-destroy", "off"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )

    # tmux session 의 cols/rows 를 client xterm size 와 동일하게 resize. mismatch 시
    # capture-pane / attach 출력의 grid 가 xterm parser 의 viewport 와 안 맞아 정렬 깨짐.
    # background ws (mini preview) 는 resize 박지 않음 — 작은 cols 가 session global
    # cols 강제 → 다른 큰 client 의 viewport 에 padding (·) 사고 차단.
    if tmux_session and not background_mode:
        try:
            subprocess.run(
                ["tmux", "resize-window", "-t", tmux_session, "-x", str(cols), "-y", str(rows)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=1.0,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass

    # tmux attach 직전 — history 한 번 dump 해서 ws 로 직접 보냄. attach 가 *현재
    # 화면만* 전송 (옛 출력 X). 모드 별 capture-pane scope:
    # - 일반 mode (terminal 페이지 cols 150+) : -S -3000 으로 scrollback 3000 라인.
    #   사용자가 위로 스크롤해 옛 명령 history 볼 수 있게.
    # - background mode (mini preview, cols < 150) : 현재 grid 만 (No -S). xterm 의
    #   14 rows = 현재 화면 의 마지막 N rows = claude TUI 의 *입력란 + footer* 영역.
    #   scrollback dump 면 *xterm 의 14 rows 가 옛 부분 stuck* 사고.
    history_dump: bytes | None = None
    if tmux_session:
        try:
            # -e 제거 — escape cursor-move 가 옛 cols 좌표 기반이라 새 cols 의 xterm 에서
            # 계단식 정렬 사고. plain text 만 dump (과거 색상 손실, 정렬은 OK).
            capture_cmd = ["tmux", "capture-pane", "-p", "-t", tmux_session]
            if not background_mode:
                capture_cmd[3:3] = ["-S", "-3000"]
            res = subprocess.run(
                capture_cmd,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
            if res.returncode == 0 and res.stdout:
                # capture-pane 의 plain output 은 \n (LF) 만 — xterm 은 LF 만 받으면
                # cursor col 유지 → 각 line 의 다음 줄 시작이 옛 col (계단식 정렬). CR
                # 추가해 \r\n 으로 정상 줄바꿈.
                dump_lines = res.stdout.split(b"\n")
                # background mode 시 *마지막 N lines* 만 (xterm rows + 여유). 사용자
                # 의도 = 입력란 + footer 보임 — alt-screen 의 *맨 아래* 부분. capture-pane
                # dump 전체 (24+ rows) 시 xterm 14 rows 의 *처음 14 = 위쪽 stuck* 사고.
                if background_mode:
                    # 정확 xterm rows 만 — viewport 가득 + 마지막 line = footer/입력란
                    dump_lines = dump_lines[-rows:]
                stdout_trim = b"\n".join(dump_lines)
                # ANSI clear screen + cursor home (\x1b[2J\x1b[H) prefix — frontend
                # xterm 의 *옛 잔재* 차단. AgentCardTerminal / WebTerminal 모두 코드
                # 변경 없이 xterm 자동 reset.
                dump_payload = b"\x1b[2J\x1b[H" + stdout_trim.replace(b"\n", b"\r\n")
                history_dump = dump_payload
                log.info("ws-terminal: history dump %d bytes session=%s background=%s lines=%d", len(history_dump), tmux_session, background_mode, len(dump_lines))
        except (subprocess.TimeoutExpired, OSError) as e:
            log.warning("ws-terminal: capture-pane failed err=%s", e)

    pid, fd = pty.fork()
    if pid == 0:
        # child process — exec shell or tmux attach. 이 분기는 절대 return 안 함.
        env = os.environ.copy()
        env["LANG"] = "ko_KR.UTF-8"
        env["LC_ALL"] = "ko_KR.UTF-8"
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        if agent_id:
            env["AIDESK_AGENT_ID"] = agent_id
        try:
            os.chdir(cwd)
        except OSError:
            pass
        try:
            if tmux_session:
                # tmux attach — ws 끊김 = detach (session + claude 살아있음).
                os.execvpe("tmux", ["tmux", "attach-session", "-t", tmux_session], env)
            else:
                # 옛 동작 (tmux 없거나 미지정) — 직접 shell. ws 끊김 시 종료.
                os.execvpe(shell, [shell, "-il"], env)
        except OSError as e:
            print(f"[aidesk-web-pty] exec failed: {e}", flush=True)
            os._exit(127)

    # parent
    _set_winsize(fd, rows, cols)
    # history dump 전송 (attach 출력 전). client xterm 의 buffer 가 옛 history 갖게.
    if history_dump:
        try:
            await ws.send_bytes(history_dump + b"\r\n")
        except Exception as e:  # noqa: BLE001
            log.warning("ws-terminal: history send failed err=%s", e)

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
