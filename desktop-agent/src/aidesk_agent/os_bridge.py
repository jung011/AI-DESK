"""로컬 OS 조작 — 백엔드의 AgentService.openTerminal/openVscode/browseWorkspace 를 Python 으로 포팅.

macOS 전용. osascript + Terminal.app + tmux + `code` 바이너리 조합으로 동작.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
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


def _build_open_terminal_script(workspace_dir: str, tmux_session: str, title: str, claude_cmd: str) -> str:
    """백엔드 AgentService.openTerminal 의 AppleScript 를 그대로 옮긴 것.

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
    script = _build_open_terminal_script(workspace_dir, tmux_session, title, claude_cmd)
    try:
        subprocess.Popen(["osascript", "-e", script])
    except OSError as e:
        log.warning("open_terminal failed: %s", e)
        return 4, f"osascript 실행 실패: {e}"
    log.info("open_terminal: dir=%s session=%s past=%s", workspace_dir, tmux_session, has_past)
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
