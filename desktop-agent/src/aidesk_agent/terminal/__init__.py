"""외부 터미널 (iTerm2 우선, Terminal.app fallback).

helper 가 frontend `/api/open-terminal` 처리할 때 사용. AI 별 tmux 세션을
별도 터미널 윈도우에 attach 해 사용자가 직접 입력·복사할 수 있도록 한다.

public:
    open_terminal — dispatcher (AIDESK_TERMINAL_APP env 또는 iTerm 설치 여부)
    ensure_iterm_dynamic_profile — helper 시작 시 한 번 호출, iTerm Title Components 적용
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from .._shared import has_past_session
from .iterm import (
    build_open_iterm_script,
    ensure_iterm_dynamic_profile,
    iterm_installed,
)
from .apple_terminal import build_open_terminal_script

__all__ = ["open_terminal", "ensure_iterm_dynamic_profile"]

log = logging.getLogger(__name__)


def _ensure_tmux_session(tmux_session: str, workspace_dir: str, claude_cmd: str) -> None:
    """tmux session 을 helper python 환경에서 직접 detached 로 생성.

    AppleScript 가 *iTerm 의 raw zsh prompt* 에 `tmux new-session ...` 명령을 write 하면
    환경에 따라 zsh 가 그 명령을 그대로 raw text 로 표시하거나 path/escape 미인식으로
    실패하는 케이스가 있다 (우드 mac 의 .config/tmux + continuum + resurrect 조합).

    그래서 *명령 자체* 는 helper python 의 깨끗한 env 에서 실행. iTerm 은 이미 생성된
    session 에 `tmux attach-session -t <name>` 만 하면 환경 의존 issue 없음.

    이미 같은 이름 session 이 있으면 *kill 후 fresh 재생성* — stale session (continuum
    복원 등) 이 첫 명령 (claude -c) 을 skip 한 채 zsh 만 남아있는 케이스 차단.
    """
    # 기존 stale session 정리 (있을 때만, has-session 결과로 분기)
    has_rc = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode
    if has_rc == 0:
        # 같은 이름 session 존재 — claude 실행 중인지 확인 후 결정.
        # pane_current_command 이 claude 류면 그대로 두고 attach 만, 아니면 kill 후 재생성.
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", tmux_session, "#{pane_current_command}"],
            capture_output=True, text=True,
        )
        cmd = (result.stdout or "").strip()
        # claude binary 이름은 version (예: 2.1.177) 으로 나오기도 함. 'claude' literal 또는 숫자 시작이면 claude 추정.
        is_claude_running = cmd == "claude" or (cmd and cmd[0].isdigit())
        if not is_claude_running:
            log.info("tmux: kill stale session %s (current cmd=%s)", tmux_session, cmd or "<empty>")
            subprocess.run(["tmux", "kill-session", "-t", tmux_session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            log.info("tmux: reuse session %s (claude already running)", tmux_session)
            return
    log.info("tmux: create new-session -d -s %s -c %s '%s'", tmux_session, workspace_dir, claude_cmd)
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", tmux_session, "-c", workspace_dir, claude_cmd],
        check=False,
    )


def open_terminal(workspace_dir: str, tmux_session: str, title: str = "") -> tuple[int, str]:
    """Return (rc, message). rc: 0=ok, 2=invalid workspace, 4=launch failed.

    흐름:
      1. helper python 이 tmux new-session -d (detached) 로 session 직접 생성 — env / cwd /
         첫 명령 모두 helper 의 깨끗한 환경에서 처리 (raw zsh prompt 의존 X).
      2. iTerm AppleScript 는 *attach* 만 — `tmux attach-session -t <name>`.

    AIDESK_TERMINAL_APP env 로 강제 지정 가능 (`iterm` 또는 `terminal`).
    미지정이면 iTerm 설치 여부로 결정 (있으면 iTerm 우선).
    """
    if not workspace_dir or not Path(workspace_dir).is_dir():
        return 2, "workspaceDir 가 비어있거나 존재하지 않습니다."
    if not tmux_session:
        return 2, "tmuxSession 이 비어있습니다."
    claude_cmd = "claude -c" if has_past_session(workspace_dir) else "claude"

    # 1) helper python 이 tmux session 직접 생성 (환경 독립).
    try:
        _ensure_tmux_session(tmux_session, workspace_dir, claude_cmd)
    except OSError as e:
        log.warning("tmux session create failed: %s", e)
        return 4, f"tmux session 생성 실패: {e}"

    # 2) iTerm/Terminal 은 attach 만.
    forced = os.environ.get("AIDESK_TERMINAL_APP", "").strip().lower()
    use_iterm = (forced == "iterm") or (forced == "" and iterm_installed())
    if use_iterm:
        script = build_open_iterm_script(workspace_dir, tmux_session, title, claude_cmd)
        app_name = "iTerm"
    else:
        script = build_open_terminal_script(workspace_dir, tmux_session, title, claude_cmd)
        app_name = "Terminal"
    try:
        subprocess.Popen(["osascript", "-e", script])
    except OSError as e:
        log.warning("open_terminal failed: %s", e)
        return 4, f"osascript 실행 실패: {e}"
    log.info(
        "open_terminal: app=%s dir=%s session=%s",
        app_name, workspace_dir, tmux_session,
    )
    return 0, "ok"
