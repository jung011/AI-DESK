"""iTerm2 통합 — Dynamic Profile + AppleScript 빌더."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .._shared import applescript_escape

log = logging.getLogger(__name__)

_ITERM_APP_PATH = Path("/Applications/iTerm.app")
_AIDESK_ITERM_PROFILE_NAME = "AI Desk"
_AIDESK_ITERM_PROFILE_GUID = "AIDESK-PROFILE-iTerm-Dynamic-001"
_AIDESK_ITERM_PROFILE_PATH = (
    Path.home() / "Library/Application Support/iTerm2/DynamicProfiles/aidesk.json"
)


def iterm_installed() -> bool:
    """iTerm.app 설치 여부 — 우선 사용할 대상 결정에 사용."""
    return _ITERM_APP_PATH.exists()


def ensure_iterm_dynamic_profile() -> None:
    """iTerm Dynamic Profile 'AI Desk' 를 보장 (idempotent, 매 helper 시작 시 호출).

    Title Components = 1 (Session Name only) — 외부 터미널 열기 시 우리가 AppleScript
    로 set 한 session name (= AI 에이전트 이름) 이 그대로 iTerm 의 title bar 에 표시.
    'Dynamic Profile Parent Name' = Default → 사용자의 Default profile 다른 옵션
    (font, color, mouse 등) 모두 그대로 상속. 우리가 override 하는 건 Title Components 뿐.

    이 함수가 없으면 사용자가 iTerm Preferences GUI 에서 직접 Title 설정을 만져야
    AI 이름이 title bar 에 표시됨. helper 가 자동 생성하면 모든 PC 에서 통일된
    동작 가능 (우드 등 다른 사용자도 .pkg 설치만으로 끝).
    """
    if not iterm_installed():
        return
    profile = {
        "Profiles": [{
            "Name": _AIDESK_ITERM_PROFILE_NAME,
            "Guid": _AIDESK_ITERM_PROFILE_GUID,
            "Title Components": 1,
            "Dynamic Profile Parent Name": "Default",
        }],
    }
    try:
        _AIDESK_ITERM_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _AIDESK_ITERM_PROFILE_PATH.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False)
        )
        log.info("iTerm Dynamic Profile 적용: %s", _AIDESK_ITERM_PROFILE_PATH)
    except OSError as e:
        log.warning("iTerm Dynamic Profile 작성 실패: %s", e)


def build_open_iterm_script(
    workspace_dir: str, tmux_session: str, title: str, claude_cmd: str
) -> str:
    """iTerm (iTerm2) 용 AppleScript.

    iTerm 의 native 우클릭 메뉴 / mouse handling 이 Terminal.app 보다 풍부해서
    tmux mouse 옵션과 무관하게 사용자가 편하게 복사·붙여넣기 가능.

    동작 우선순위:
      1) 같은 AI 의 iTerm session (= session name 이 우리가 set 한 tabTitle 과 일치)
         찾아 활성화. tty 매칭만 쓰던 이전 패턴은 카랑이/챗봇 같이 ttys003 등 동일 tty
         값이 다른 agent 의 attach 와 충돌하던 케이스가 있어 name 매칭을 1순위로.
      2) 1) 이 실패해도 같은 tmux session 에 attach 된 client tty 가 있으면 tty 매칭 fallback.
         (사용자가 iTerm 안에서 session 을 직접 rename 한 케이스 보완)
      3) 둘 다 실패면 새 *윈도우* 생성 (AI 별 분리 워크플로)
      4) current session 에 cd + tmux 명령 write + 탭 제목 set
    """
    dir_esc = applescript_escape(workspace_dir)
    title_esc = applescript_escape(title or tmux_session)
    return (
        f'set sessionName to "{tmux_session}"\n'
        f'set wsQuoted to quoted form of "{dir_esc}"\n'
        f'set tabTitle to "{title_esc}"\n'
        # helper python 이 이미 detached 로 tmux session 을 생성해뒀으므로 iTerm 은
        # attach 만 한다. 옛 패턴 (cd && tmux new-session -A -s ... 'claude') 은 raw zsh
        # prompt 환경 차이 (continuum/resurrect, .tmux.conf 의 detach-on-destroy 등) 에
        # 따라 명령이 그대로 raw text 로 출력되거나 stale 세션에 attach 만 되는 케이스가
        # 있었음. attach 만 하면 환경 무관 동작.
        f'set shellCmd to "tmux attach-session -t " & sessionName & "; exit 0"\n'
        'set clientTty to ""\n'
        'try\n'
        '  set clientTty to do shell script "tmux list-clients -t " & sessionName & " -F \'#{client_tty}\' 2>/dev/null | head -n 1"\n'
        'end try\n'
        # iTerm 가 *활성 윈도우* 가 있는 상태였는지 검사. 'is running' 으로는 부족 —
        # process 가 idle 로 살아있고 windows=0 인 케이스가 흔해서 (사용자가 마지막 창 닫은 직후 등)
        # 그땐 activate 시 default profile 의 빈 zsh 가 자동 생성됨. windows>0 판정이 정확.
        'set hadWindows to false\n'
        'try\n'
        '  tell application "iTerm" to if (count of windows) > 0 then set hadWindows to true\n'
        'end try\n'
        'tell application "iTerm"\n'
        '  activate\n'
        '  -- launch/wake 직후 자동 생성된 default-profile 윈도우의 id 를 기억해두고, AI Desk\n'
        '  -- 윈도우 먼저 만든 후 그 자동 윈도우만 닫음 (close-first 면 iTerm "Quit when no\n'
        '  -- open windows" 옵션에 따라 iTerm 가 quit 될 수 있어 launch loop 발생).\n'
        '  set autoWinIds to {}\n'
        '  if not hadWindows then\n'
        '    delay 0.6\n'
        '    try\n'
        '      repeat with w in windows\n'
        '        try\n'
        '          set end of autoWinIds to id of w\n'
        '        end try\n'
        '      end repeat\n'
        '    end try\n'
        '  end if\n'
        '  set foundIt to false\n'
        '  -- 1순위: session name 매칭. 우리가 set name 으로 박은 tabTitle 과 일치 = 같은 AI 창.\n'
        '  -- tty 매칭만 쓸 때 ttys003 같은 동일 tty 값이 다른 agent 와 충돌하던 케이스 차단.\n'
        '  if hadWindows then\n'
        '    repeat with w in windows\n'
        '      repeat with t in tabs of w\n'
        '        repeat with s in sessions of t\n'
        '          try\n'
        '            if name of s is tabTitle then\n'
        '              select w\n'
        '              select t\n'
        '              select s\n'
        '              set foundIt to true\n'
        '              exit repeat\n'
        '            end if\n'
        '          end try\n'
        '        end repeat\n'
        '        if foundIt then exit repeat\n'
        '      end repeat\n'
        '      if foundIt then exit repeat\n'
        '    end repeat\n'
        '  end if\n'
        '  -- 2순위: tty 매칭 fallback. 사용자가 iTerm 에서 session 을 직접 rename 해 1순위가\n'
        '  -- 실패한 경우만 진입. 여기서도 다른 session 충돌 가능성은 있지만 1순위로 거의 흡수됨.\n'
        '  if not foundIt and hadWindows and clientTty is not "" then\n'
        '    repeat with w in windows\n'
        '      repeat with t in tabs of w\n'
        '        repeat with s in sessions of t\n'
        '          try\n'
        '            if tty of s is clientTty then\n'
        '              select w\n'
        '              select t\n'
        '              select s\n'
        '              set foundIt to true\n'
        '              exit repeat\n'
        '            end if\n'
        '          end try\n'
        '        end repeat\n'
        '        if foundIt then exit repeat\n'
        '      end repeat\n'
        '      if foundIt then exit repeat\n'
        '    end repeat\n'
        '  end if\n'
        '  if not foundIt then\n'
        '    create window with profile "AI Desk"\n'
        '    tell current session of current window\n'
        '      write text shellCmd\n'
        '    end tell\n'
        '    -- iTerm Profile 의 Title 정책에 따라 set name 이 무시되는 케이스가 있어서\n'
        '    -- OSC 0 escape sequence (ESC ]0; TITLE BEL) 를 직접 send 해 title bar 강제 갱신.\n'
        '    -- tmux 의 set-titles 가 default off 라 attach 후에도 우리 값 유지됨.\n'
        '    delay 1.0\n'
        '    try\n'
        '      set ESC to character id 27\n'
        '      set BEL to character id 7\n'
        '      tell current session of current window\n'
        '        write text (ESC & "]0;" & tabTitle & BEL) without newline\n'
        '      end tell\n'
        '    end try\n'
        '    try\n'
        '      set name of current session of current window to tabTitle\n'
        '    end try\n'
        '    try\n'
        '      set name of current tab of current window to tabTitle\n'
        '    end try\n'
        '  end if\n'
        '  -- AI Desk 윈도우 생성이 끝난 후, launch 시 따라온 default zsh 윈도우들을 정리.\n'
        '  -- iTerm 가 *지금은* 우리 AI Desk 윈도우를 갖고 있으므로 last-window-close 로 quit 되지 않음.\n'
        '  repeat with wid in autoWinIds\n'
        '    try\n'
        '      tell (first window whose id is (wid as integer)) to close\n'
        '    end try\n'
        '  end repeat\n'
        'end tell\n'
    )
