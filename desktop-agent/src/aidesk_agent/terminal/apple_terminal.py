"""macOS 기본 Terminal.app fallback — iTerm 미설치 환경 전용."""
from __future__ import annotations

from .._shared import applescript_escape


def build_open_terminal_script(
    workspace_dir: str, tmux_session: str, title: str, claude_cmd: str
) -> str:
    """백엔드 AgentService.openTerminal 의 AppleScript 를 그대로 옮긴 것 (Terminal.app fallback).

    iTerm 미설치 환경에서만 사용. iTerm 이 있으면 iterm.build_open_iterm_script 가 우선.

    동작 우선순위:
      1) 같은 tmux 세션에 attach 된 Terminal tab 이 있으면 그 윈도우/탭 활성화
      2) Terminal 가동 중이면 새 탭에서 cd + tmux new-session
      3) Terminal 미가동이면 launch 후 기본 윈도우 재사용
    """
    dir_esc = applescript_escape(workspace_dir)
    title_esc = applescript_escape(title or tmux_session)
    return (
        f'set sessionName to "{tmux_session}"\n'
        f'set wsQuoted to quoted form of "{dir_esc}"\n'
        f'set tabTitle to "{title_esc}"\n'
        # helper python 이 detached tmux session 미리 생성 — Terminal 은 attach 만.
        f'set shellCmd to "tmux attach-session -t " & sessionName & "; exit 0"\n'
        'set termRunning to false\n'
        'try\n'
        '  do shell script "pgrep -x Terminal > /dev/null"\n'
        '  set termRunning to true\n'
        'end try\n'
        'set clientTty to ""\n'
        'try\n'
        '  set clientTty to do shell script "tmux list-clients -t " & sessionName & " -F \'#{client_tty}\' 2>/dev/null | head -n 1"\n'
        'end try\n'
        'if clientTty is not "" then\n'
        '  tell application "Terminal"\n'
        '    activate\n'
        '    repeat with w in windows\n'
        '      repeat with t in tabs of w\n'
        '        try\n'
        '          if (tty of t) is clientTty then\n'
        '            set frontmost of w to true\n'
        '            set selected of t to true\n'
        '            return\n'
        '          end if\n'
        '        end try\n'
        '      end repeat\n'
        '    end repeat\n'
        '  end tell\n'
        'end if\n'
        'if termRunning then\n'
        '  tell application "Terminal"\n'
        '    activate\n'
        '    set newTab to do script shellCmd\n'
        '    try\n'
        '      set font size of newTab to 14\n'
        '    end try\n'
        '    try\n'
        '      set custom title of newTab to tabTitle\n'
        '    end try\n'
        '  end tell\n'
        'else\n'
        '  tell application "Terminal"\n'
        '    launch\n'
        '    repeat 30 times\n'
        '      if (count windows) > 0 then exit repeat\n'
        '      delay 0.1\n'
        '    end repeat\n'
        '    activate\n'
        '    if (count windows) > 0 then\n'
        '      set newTab to do script shellCmd in selected tab of front window\n'
        '    else\n'
        '      set newTab to do script shellCmd\n'
        '    end if\n'
        '    try\n'
        '      set font size of newTab to 14\n'
        '    end try\n'
        '    try\n'
        '      set custom title of newTab to tabTitle\n'
        '    end try\n'
        '  end tell\n'
        'end if\n'
    )
