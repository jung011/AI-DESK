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


def open_terminal(workspace_dir: str, tmux_session: str, title: str = "") -> tuple[int, str]:
    """Return (rc, message). rc: 0=ok, 2=invalid workspace, 4=launch failed.

    AIDESK_TERMINAL_APP env 로 강제 지정 가능 (`iterm` 또는 `terminal`).
    미지정이면 iTerm 설치 여부로 결정 (있으면 iTerm 우선).
    """
    if not workspace_dir or not Path(workspace_dir).is_dir():
        return 2, "workspaceDir 가 비어있거나 존재하지 않습니다."
    if not tmux_session:
        return 2, "tmuxSession 이 비어있습니다."
    claude_cmd = "claude -c" if has_past_session(workspace_dir) else "claude"
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
