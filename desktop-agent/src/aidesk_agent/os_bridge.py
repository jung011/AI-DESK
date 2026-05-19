"""로컬 OS 조작 — 백엔드의 AgentService.openTerminal/openVscode/browseWorkspace 를 Python 으로 포팅.

macOS 전용. osascript + Terminal.app + tmux + `code` 바이너리 조합으로 동작.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)

_ESCAPE_RE = re.compile(r"[^A-Za-z0-9_]")


def _encoded_project_dir(workspace_dir: str) -> Path:
    escaped = _ESCAPE_RE.sub("-", workspace_dir)
    return Path.home() / ".claude" / "projects" / escaped


def _has_past_session(workspace_dir: str) -> bool:
    """`~/.claude/projects/{escaped}/` 안에 `.jsonl` 이 하나라도 있으면 옛 대화가 있다고 본다."""
    project_dir = _encoded_project_dir(workspace_dir)
    if not project_dir.is_dir():
        return False
    for p in project_dir.rglob("*.jsonl"):
        if p.is_file():
            return True
    return False


def _applescript_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _iterm_installed() -> bool:
    """iTerm.app 설치 여부 — 우선 사용할 대상 결정에 사용."""
    return Path("/Applications/iTerm.app").exists()


_AIDESK_ITERM_PROFILE_NAME = "AI Desk"
_AIDESK_ITERM_PROFILE_GUID = "AIDESK-PROFILE-iTerm-Dynamic-001"
_AIDESK_ITERM_PROFILE_PATH = (
    Path.home() / "Library/Application Support/iTerm2/DynamicProfiles/aidesk.json"
)


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
    if not _iterm_installed():
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


def _build_open_iterm_script(workspace_dir: str, tmux_session: str, title: str, claude_cmd: str) -> str:
    """iTerm (iTerm2) 용 AppleScript.

    iTerm 의 native 우클릭 메뉴 / mouse handling 이 Terminal.app 보다 풍부해서
    tmux mouse 옵션과 무관하게 사용자가 편하게 복사·붙여넣기 가능.

    동작 우선순위:
      1) 같은 tmux 세션에 이미 attach 된 iTerm session 이 있으면 그 윈도우/탭 활성화
         (tmux list-clients 의 client_tty 와 iTerm session 의 tty 매칭)
      2) 없으면 새 *윈도우* 생성 (AI 별 분리 워크플로)
      3) current session 에 cd + tmux 명령 write + 탭 제목 set
    """
    dir_esc = _applescript_escape(workspace_dir)
    title_esc = _applescript_escape(title or tmux_session)
    return (
        f'set sessionName to "{tmux_session}"\n'
        f'set wsQuoted to quoted form of "{dir_esc}"\n'
        f'set tabTitle to "{title_esc}"\n'
        f'set shellCmd to "cd " & wsQuoted & " && tmux new-session -A -s " & sessionName & " \'{claude_cmd}\'; exit 0"\n'
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
        '  if hadWindows and clientTty is not "" then\n'
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


def _build_open_terminal_script(workspace_dir: str, tmux_session: str, title: str, claude_cmd: str) -> str:
    """백엔드 AgentService.openTerminal 의 AppleScript 를 그대로 옮긴 것 (Terminal.app fallback).

    iTerm 미설치 환경에서만 사용. iTerm 이 있으면 _build_open_iterm_script 가 우선.

    동작 우선순위:
      1) 같은 tmux 세션에 attach 된 Terminal tab 이 있으면 그 윈도우/탭 활성화
      2) Terminal 가동 중이면 새 탭에서 cd + tmux new-session
      3) Terminal 미가동이면 launch 후 기본 윈도우 재사용
    """
    dir_esc = _applescript_escape(workspace_dir)
    title_esc = _applescript_escape(title or tmux_session)
    return (
        f'set sessionName to "{tmux_session}"\n'
        f'set wsQuoted to quoted form of "{dir_esc}"\n'
        f'set tabTitle to "{title_esc}"\n'
        f'set shellCmd to "cd " & wsQuoted & " && tmux new-session -A -s " & sessionName & " \'{claude_cmd}\'; exit 0"\n'
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


def open_terminal(workspace_dir: str, tmux_session: str, title: str = "") -> tuple[int, str]:
    """Return (rc, message). rc: 0=ok, 2=invalid workspace, 4=launch failed."""
    if not workspace_dir or not Path(workspace_dir).is_dir():
        return 2, "workspaceDir 가 비어있거나 존재하지 않습니다."
    if not tmux_session:
        return 2, "tmuxSession 이 비어있습니다."
    has_past = _has_past_session(workspace_dir)
    claude_cmd = "claude -c" if has_past else "claude"
    # iTerm 우선 — 사용자가 명시적으로 AIDESK_TERMINAL_APP=Terminal 로 강제 지정 가능.
    forced = os.environ.get("AIDESK_TERMINAL_APP", "").strip().lower()
    use_iterm = (forced == "iterm") or (forced == "" and _iterm_installed())
    if use_iterm:
        script = _build_open_iterm_script(workspace_dir, tmux_session, title, claude_cmd)
        app_name = "iTerm"
    else:
        script = _build_open_terminal_script(workspace_dir, tmux_session, title, claude_cmd)
        app_name = "Terminal"
    try:
        subprocess.Popen(["osascript", "-e", script])
    except OSError as e:
        log.warning("open_terminal failed: %s", e)
        return 4, f"osascript 실행 실패: {e}"
    log.info("open_terminal: app=%s dir=%s session=%s past=%s",
             app_name, workspace_dir, tmux_session, has_past)
    return 0, "ok"


# ──────────────────────────────────────────────────────────────────────────────
# VSCode
# ──────────────────────────────────────────────────────────────────────────────


def _locate_vscode_bundled() -> str | None:
    """`code` CLI 가 PATH 에 없을 때 VSCode.app 번들 안의 code 바이너리를 찾는다."""
    try:
        out = subprocess.run(
            ["mdfind", "kMDItemCFBundleIdentifier == 'com.microsoft.VSCode'"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        candidate = Path(line.strip()) / "Contents" / "Resources" / "app" / "bin" / "code"
        if candidate.is_file():
            return str(candidate)
    return None


def open_vscode(workspace_dir: str) -> tuple[int, str]:
    if not workspace_dir or not Path(workspace_dir).is_dir():
        return 2, "workspaceDir 가 비어있거나 존재하지 않습니다."

    # 1) PATH 의 code
    code_bin = shutil.which("code")
    if code_bin:
        try:
            subprocess.Popen([code_bin, workspace_dir])
            log.info("open_vscode (PATH): dir=%s", workspace_dir)
            return 0, "ok"
        except OSError:
            pass

    # 2) VSCode.app 번들 안의 code 바이너리
    bundled = _locate_vscode_bundled()
    if bundled:
        try:
            subprocess.Popen([bundled, workspace_dir])
            log.info("open_vscode (bundled): dir=%s via %s", workspace_dir, bundled)
            return 0, "ok"
        except OSError as e:
            log.warning("open_vscode bundled failed: %s", e)

    return 4, (
        "VSCode 를 찾지 못했습니다. /Applications/Visual Studio Code.app 에 설치되어 있는지, "
        "또는 VSCode 명령 팔레트에서 'Shell Command: Install code command in PATH' 를 실행했는지 확인하세요."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 폴더 선택 다이얼로그
# ──────────────────────────────────────────────────────────────────────────────


def _tmux_client_tty(session: str) -> str:
    """tmux 세션에 attach 된 첫 번째 클라이언트의 tty 경로. 없으면 빈 문자열."""
    if not session:
        return ""
    try:
        proc = subprocess.run(
            ["tmux", "list-clients", "-t", session, "-F", "#{client_tty}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    out = proc.stdout.strip()
    if not out or out.startswith(("can't find", "no clients")):
        return ""
    return out.splitlines()[0].strip()


def _tmux_kill_session(session: str) -> None:
    if not session:
        return
    try:
        proc = subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True,
            timeout=3,
        )
        if proc.returncode == 0:
            log.info("tmux session killed: %s", session)
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning("tmux kill-session failed for %s: %s", session, e)


def _close_terminal_tab_by_tty(tty: str) -> None:
    """Terminal.app 의 윈도우 중 주어진 tty 를 갖는 것을 닫는다. 없으면 조용히 패스."""
    if not tty:
        return
    # tmux 클라이언트 disconnect → zsh `; exit 0` → logout 처리 시간 확보.
    time.sleep(0.4)
    tty_esc = tty.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Terminal"\n'
        '  repeat with w in windows\n'
        '    try\n'
        '      set matched to false\n'
        '      repeat with t in tabs of w\n'
        '        try\n'
        f'          if (tty of t) is "{tty_esc}" then\n'
        '            set matched to true\n'
        '            exit repeat\n'
        '          end if\n'
        '        end try\n'
        '      end repeat\n'
        '      if matched then\n'
        '        close w saving no\n'
        '      end if\n'
        '    end try\n'
        '  end repeat\n'
        'end tell\n'
    )
    try:
        subprocess.Popen(["osascript", "-e", script])
        log.info("Terminal window close requested: tty=%s", tty)
    except OSError as e:
        log.warning("close terminal failed: %s", e)


def cleanup_agent(
    tmux_session: str,
    workspace_dir: str | None = None,
    purge_history: bool = False,
) -> tuple[int, str]:
    """에이전트 삭제 시 호출 — tmux 세션 + 그에 attach 된 Terminal 윈도우 정리.

    purge_history=True + workspace_dir 가 주어지면 `~/.claude/projects/{escaped}/` 의
    Claude 대화 jsonl 도 함께 삭제. 같은 워크스페이스 경로로 새 에이전트 생성 시 옛 대화가
    `claude -c` 로 살아오는 걸 막는 용도.

    실패해도 백엔드 DB 삭제 자체엔 영향 없도록 비-치명적으로 처리.
    """
    if not tmux_session:
        if workspace_dir and purge_history:
            _purge_claude_history(workspace_dir)
            return 0, "no tmux session; history purged"
        return 0, "no-op (empty tmuxSession)"
    tty = _tmux_client_tty(tmux_session)
    _tmux_kill_session(tmux_session)
    if tty:
        _close_terminal_tab_by_tty(tty)
    purged = False
    if workspace_dir and purge_history:
        purged = _purge_claude_history(workspace_dir)
    log.info(
        "cleanup_agent: session=%s tty=%s purgeHistory=%s purged=%s",
        tmux_session, tty or "(none)", purge_history, purged,
    )
    return 0, "ok"


def _purge_claude_history(workspace_dir: str) -> bool:
    """`~/.claude/projects/{escaped}/` 의 jsonl 대화 기록 전부 제거.

    디렉토리 자체를 삭제하지 않고 jsonl 파일들만 제거 — Claude Code 가 이 폴더를
    재생성하는 데 의존하므로 폴더 보존이 안전 (사이드카 디렉토리 정리 안 함).
    """
    project_dir = _encoded_project_dir(workspace_dir)
    if not project_dir.is_dir():
        return False
    removed = 0
    for p in project_dir.rglob("*.jsonl"):
        if not p.is_file():
            continue
        try:
            p.unlink()
            removed += 1
        except OSError as e:
            log.warning("purge_history: failed to remove %s: %s", p, e)
    log.info("purge_history: removed %d jsonl(s) from %s", removed, project_dir)
    return removed > 0


def browse_workspace() -> tuple[int, str]:
    """macOS 폴더 선택 다이얼로그. 사용자 취소시 빈 문자열 반환."""
    script = 'POSIX path of (choose folder with prompt "워크스페이스 폴더를 선택하세요")'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,  # 사용자가 다이얼로그 떠 있는 동안 충분히 대기
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return 4, f"폴더 다이얼로그 실행 실패: {e}"
    # 사용자 취소: returncode 1, stderr 에 -128
    if proc.returncode != 0:
        return 0, ""
    path = proc.stdout.strip()
    # POSIX path of 는 끝에 '/' 가 붙는 경우가 있어 정리
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return 0, path


def browse_file(prompt: str = "파일을 선택하세요") -> tuple[int, str]:
    """macOS 파일 선택 다이얼로그. 사용자 취소시 빈 문자열 반환."""
    # `choose file` 은 폴더가 아닌 파일을 고름. type filter 없이 모든 파일 허용.
    prompt_escaped = prompt.replace('"', '\\"')
    script = f'POSIX path of (choose file with prompt "{prompt_escaped}")'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return 4, f"파일 다이얼로그 실행 실패: {e}"
    if proc.returncode != 0:
        return 0, ""  # 사용자 취소
    return 0, proc.stdout.strip()


# kaflix-a2a / kaflix-channel MCP 서버는 (me) 가 지정한 A2A 워크스페이스에만 노출.
# scope_workspace 가 ~/.claude.json 의 두 항목을 새 워크스페이스의 projects 엔트리로 이동.
_SCOPED_MCP_SERVERS = ("kaflix-a2a", "kaflix-channel")

# 사내 도구 (kaflix) MCP 정의 영구 캐시 위치 — 한 번 회수해두면 워크스페이스 폴더 삭제,
# DB 초기화, 옛 워크스페이스 분실 등 어떤 케이스에도 정의 보존. 사용자가 사내 도구를
# 재실행해 글로벌 mcpServers 가 갱신되면 다음 scope_workspace 호출 시 캐시도 갱신.
_KAFLIX_MCP_CACHE = Path.home() / ".aidesk" / "kaflix-mcp.json"


def _read_cached_kaflix_definitions() -> dict:
    """캐시에서 kaflix-* MCP 정의를 읽는다. 없거나 깨졌으면 빈 dict."""
    if not _KAFLIX_MCP_CACHE.is_file():
        return {}
    try:
        cfg = json.loads(_KAFLIX_MCP_CACHE.read_text(encoding="utf-8"))
        servers = (cfg.get("mcpServers") or {}) if isinstance(cfg, dict) else {}
        return servers if isinstance(servers, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        log.warning("kaflix cache read failed: %s", e)
        return {}


def _write_cached_kaflix_definitions(servers: dict) -> None:
    """회수한 kaflix-* 정의를 캐시에 영구 저장."""
    if not servers:
        return
    try:
        _KAFLIX_MCP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if _KAFLIX_MCP_CACHE.is_file():
            try:
                cfg = json.loads(_KAFLIX_MCP_CACHE.read_text(encoding="utf-8"))
                if isinstance(cfg, dict):
                    existing = (cfg.get("mcpServers") or {})
                    if not isinstance(existing, dict):
                        existing = {}
            except json.JSONDecodeError:
                existing = {}
        existing.update(servers)
        _KAFLIX_MCP_CACHE.write_text(
            json.dumps({"mcpServers": existing}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        log.info("kaflix cache 갱신: %s (path=%s)", list(servers.keys()), _KAFLIX_MCP_CACHE)
    except OSError as e:
        log.warning("kaflix cache write failed: %s", e)


# (me) 워크스페이스에서 claude 가 매번 사용자 승인을 묻지 않도록 미리 허용해 둘 MCP 도구.
# settings.local.json 의 permissions.allow 에 자동 추가된다.
_DEFAULT_ALLOWED_TOOLS = (
    "mcp__aidesk-channel__send_to",
    "mcp__aidesk-channel__reply",
    "mcp__aidesk-channel__check_inbox",
    "mcp__aidesk-channel__list_agents",
    "mcp__kaflix-a2a",       # server prefix — claude wildcard 지원 시 모든 도구 허용
    "mcp__kaflix-channel",
)


def _write_workspace_mcp_json(workspace_dir: str, servers: dict) -> None:
    """워크스페이스 안 `.mcp.json` 에 mcpServers 정의 머지 — 워크스페이스 자족.

    `~/.claude.json` 의 projects[<path>].mcpServers 이동 대신 워크스페이스 디렉토리
    안에 직접 정의를 둔다. 사용자가 워크스페이스 폴더를 삭제하면 정의도 같이
    사라지므로 글로벌 영역에 잔재가 남지 않는다.

    기존 `.mcp.json` 이 있으면 우리 키만 갱신, 다른 키는 보존.
    """
    mcp_path = Path(workspace_dir) / ".mcp.json"
    try:
        if mcp_path.exists():
            cfg = json.loads(mcp_path.read_text(encoding="utf-8"))
            if not isinstance(cfg, dict):
                cfg = {}
        else:
            cfg = {}
        mcp_servers = cfg.setdefault("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            mcp_servers = {}
            cfg["mcpServers"] = mcp_servers
        for name, defn in servers.items():
            mcp_servers[name] = defn
        mcp_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log.info(
            "scope_workspace: .mcp.json 작성 ws=%s servers=%s",
            workspace_dir, list(servers.keys()),
        )
    except (OSError, json.JSONDecodeError) as e:
        log.warning("scope_workspace: .mcp.json 작성 실패 ws=%s err=%s", workspace_dir, e)


def _ensure_workspace_allowed_tools(workspace_dir: str) -> None:
    """워크스페이스의 `.claude/settings.local.json` 에 우리 MCP 도구 권한을 누락 없이 등록.

    사용자가 (me) 워크스페이스로 명시 선택한 시점 = aidesk-channel / kaflix-* MCP 도구
    매번 승인 다이얼로그가 뜨는 것을 방지하겠다는 동의로 간주.
    기존 항목은 보존하고 누락된 도구만 append (사용자가 직접 박은 Bash/Read 권한 등 안 건드림).
    """
    settings_dir = Path(workspace_dir) / ".claude"
    settings_path = settings_dir / "settings.local.json"
    try:
        settings_dir.mkdir(parents=True, exist_ok=True)
        if settings_path.exists():
            with settings_path.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                cfg = {}
        else:
            cfg = {}

        permissions = cfg.setdefault("permissions", {})
        if not isinstance(permissions, dict):
            permissions = {}
            cfg["permissions"] = permissions
        allow = permissions.setdefault("allow", [])
        if not isinstance(allow, list):
            allow = []
            permissions["allow"] = allow

        added = 0
        for tool in _DEFAULT_ALLOWED_TOOLS:
            if tool not in allow:
                allow.append(tool)
                added += 1

        with settings_path.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        log.info(
            "scope_workspace: settings.local.json 갱신 (added=%d, path=%s)",
            added, settings_path,
        )
    except (OSError, json.JSONDecodeError) as e:
        log.warning("scope_workspace: settings.local.json 갱신 실패: %s", e)


def scope_workspace(
    new_workspace: str,
    old_workspace: str | None = None,
    purge_previous_history: bool = False,
    me_tmux_session: str | None = None,
) -> tuple[int, str, str]:
    """A2A 워크스페이스 검증 + `~/.claude.json` 의 kaflix-* MCP scope 이동.

    백엔드가 도커 컨테이너에서 동작하므로 호스트 파일시스템에 접근 가능한 Helper 가 담당한다.

    purge_previous_history=True 면 추가로 옛 + 새 워크스페이스의 escape 디렉토리에 있는
    .jsonl 대화 기록을 모두 삭제하고, me_tmux_session 이 주어지면 그 tmux 세션도 kill.
    옛 워크스페이스를 같은 경로로 재생성한 뒤 claude --resume 으로 옛 대화가 살아오는
    케이스를 끊기 위해 사용.

    @return (rc, message, absolutePath)
        rc=0  : 성공. absolutePath 는 normalize 된 새 경로
        rc=1  : newWorkspace 가 비어 있음
        rc=2  : 디렉토리가 존재하지 않거나 디렉토리가 아님
        rc=3  : ~/.claude.json 처리 실패 (없거나 JSON 파싱 실패, 쓰기 실패)
    """
    if not new_workspace or not new_workspace.strip():
        return 1, "newWorkspace 가 비어 있습니다.", ""

    new_path = Path(new_workspace).expanduser()
    if not new_path.is_dir():
        return 2, "존재하지 않거나 디렉토리가 아닙니다.", str(new_path)

    new_abs = str(new_path.resolve())

    claude_json = Path.home() / ".claude.json"
    if not claude_json.exists():
        return 3, f"~/.claude.json 이 존재하지 않습니다: {claude_json}", new_abs

    try:
        with claude_json.open("r", encoding="utf-8") as f:
            root = json.load(f)
        if not isinstance(root, dict):
            return 3, "~/.claude.json 루트가 객체가 아닙니다.", new_abs
    except (OSError, json.JSONDecodeError) as e:
        return 3, f"~/.claude.json 읽기 실패: {e}", new_abs

    # 백업 — 같은 디렉토리에 timestamp 붙여서
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        shutil.copy(claude_json, claude_json.with_name(f".claude.json.{stamp}.bak"))
    except OSError as e:
        log.warning("scope_workspace: 백업 실패(무시): %s", e)

    # 1) 글로벌 mcpServers 에서 kaflix-* 회수
    harvested: dict = {}
    top_servers = root.get("mcpServers")
    if isinstance(top_servers, dict):
        for name in _SCOPED_MCP_SERVERS:
            if name in top_servers:
                harvested[name] = top_servers.pop(name)

    # 2) 이전 워크스페이스 projects 엔트리에서 회수 (있고 새 경로와 다를 때만)
    if old_workspace and old_workspace.strip() and old_workspace != new_abs:
        projects = root.get("projects")
        if isinstance(projects, dict):
            old_entry = projects.get(old_workspace)
            if isinstance(old_entry, dict):
                old_servers = old_entry.get("mcpServers")
                if isinstance(old_servers, dict):
                    for name in _SCOPED_MCP_SERVERS:
                        if name in old_servers and name not in harvested:
                            harvested[name] = old_servers.pop(name)

    # 2b) 옛 워크스페이스의 .mcp.json (자족 정의) 에서도 회수.
    #     워크스페이스 안 .mcp.json 방식으로 옮긴 후엔 ~/.claude.json 의 mcpServers 가
    #     비고 워크스페이스 안에 정의가 있으므로 이 경로가 필요.
    if old_workspace and old_workspace.strip() and old_workspace != new_abs:
        old_mcp_path = Path(old_workspace) / ".mcp.json"
        if old_mcp_path.is_file():
            try:
                old_cfg = json.loads(old_mcp_path.read_text(encoding="utf-8"))
                old_mcp_servers = (old_cfg.get("mcpServers") or {}) if isinstance(old_cfg, dict) else {}
                for name in _SCOPED_MCP_SERVERS:
                    if name in harvested:
                        continue
                    if name in old_mcp_servers:
                        harvested[name] = old_mcp_servers[name]
                        log.info(
                            "scope_workspace: kaflix '%s' 회수 — 옛 워크스페이스 .mcp.json (%s)",
                            name, old_mcp_path,
                        )
            except (OSError, json.JSONDecodeError) as e:
                log.warning("scope_workspace: 옛 .mcp.json 읽기 실패 %s: %s", old_mcp_path, e)

    # 2c) 위 경로들에서 못 찾은 경우 — Helper 자체 캐시 (~/.aidesk/kaflix-mcp.json) 에서 fallback.
    #     첫 회수 시 캐싱해 둔 정의로 워크스페이스 폴더 삭제, DB 초기화 등에도 복원 가능.
    if any(n not in harvested for n in _SCOPED_MCP_SERVERS):
        cached = _read_cached_kaflix_definitions()
        for name in _SCOPED_MCP_SERVERS:
            if name in harvested:
                continue
            if name in cached:
                harvested[name] = cached[name]
                log.info("scope_workspace: kaflix '%s' 회수 — helper 캐시", name)

    # 3) 새 워크스페이스에 등록.
    #    - ~/.claude.json: projects[<new>].hasTrustDialogAccepted=True 마킹 + enabledMcpjsonServers
    #      에 회수된 MCP 추가 (자동 활성화).
    #    - 워크스페이스 안 .mcp.json: 회수된 MCP 정의 자체를 자족적으로 작성.
    #    ~/.claude.json 의 projects[<new>].mcpServers 는 더 이상 박지 않음 — 워크스페이스 안
    #    .mcp.json 이 단일 소스.
    projects = root.setdefault("projects", {})
    new_entry = projects.setdefault(new_abs, {})
    new_entry["hasTrustDialogAccepted"] = True
    if harvested:
        # 자동 활성화 (사용자 동의 prompt 우회)
        enabled = new_entry.setdefault("enabledMcpjsonServers", [])
        if not isinstance(enabled, list):
            enabled = []
            new_entry["enabledMcpjsonServers"] = enabled
        for name in harvested.keys():
            if name not in enabled:
                enabled.append(name)
        # disabled 에 있으면 제거
        disabled = new_entry.get("disabledMcpjsonServers")
        if isinstance(disabled, list):
            new_entry["disabledMcpjsonServers"] = [n for n in disabled if n not in harvested]
        # 워크스페이스 안 .mcp.json 작성
        _write_workspace_mcp_json(new_abs, harvested)
        # helper 자체 캐시 갱신 — 다음 (me) 지정 시 글로벌/옛-워크스페이스 분실되어도 복원 가능
        _write_cached_kaflix_definitions(harvested)
    else:
        log.warning(
            "scope_workspace: kaflix MCP 정의가 글로벌·이전 워크스페이스 어디에도 없음 — "
            "사용자가 글로벌 mcpServers 에 한 번 등록해 두면 다음번에 자동 회수됨"
        )

    # 4) atomic write — 임시 파일에 쓰고 rename
    tmp = claude_json.with_name(f".claude.json.{stamp}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(root, f, ensure_ascii=False, indent=2)
        os.replace(tmp, claude_json)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return 3, f"~/.claude.json 쓰기 실패: {e}", new_abs

    log.info(
        "scope_workspace: %s → %s (회수 %d 건)",
        old_workspace or "(none)",
        new_abs,
        len(harvested),
    )

    # 5) 워크스페이스 안 .claude/settings.local.json 에 MCP 도구 권한 미리 등록.
    #    (~/.claude.json 의 hasTrustDialogAccepted 와 별개. 도구별 사용 승인은 이 파일에 누적.)
    _ensure_workspace_allowed_tools(new_abs)

    if purge_previous_history:
        targets = {new_abs}
        if old_workspace and old_workspace.strip():
            targets.add(old_workspace)
        for t in targets:
            try:
                _purge_claude_history(t)
            except OSError as e:
                log.warning("scope_workspace: purge failed for %s: %s", t, e)
        if me_tmux_session and me_tmux_session.strip():
            _tmux_kill_session(me_tmux_session.strip())

    return 0, "", new_abs
