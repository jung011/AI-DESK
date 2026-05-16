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

    # 3) 새 워크스페이스 projects 엔트리에 등록 — 회수된 정의 없으면 새로 등록 안 함 (사용자 환경 이상)
    if harvested:
        projects = root.setdefault("projects", {})
        new_entry = projects.setdefault(new_abs, {})
        new_servers = new_entry.setdefault("mcpServers", {})
        for name, defn in harvested.items():
            new_servers[name] = defn
    else:
        log.warning(
            "scope_workspace: kaflix MCP 정의가 글로벌·이전 워크스페이스 어디에도 없음 — 등록 스킵"
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
