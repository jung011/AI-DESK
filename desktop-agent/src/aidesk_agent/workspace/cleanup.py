"""에이전트 삭제 시 tmux 세션 + Terminal 윈도우 정리 + 옛 대화 jsonl 제거."""
from __future__ import annotations

import logging
import subprocess
import time

from .._shared import encoded_project_dir

log = logging.getLogger(__name__)


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


def tmux_kill_session(session: str) -> None:
    """tmux kill-session — scope.py 도 사용 (purge_previous_history 시 me_tmux_session kill)."""
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


def purge_claude_history(workspace_dir: str) -> bool:
    """`~/.claude/projects/{escaped}/` 의 jsonl 대화 기록 전부 제거.

    디렉토리 자체를 삭제하지 않고 jsonl 파일들만 제거 — Claude Code 가 이 폴더를
    재생성하는 데 의존하므로 폴더 보존이 안전 (사이드카 디렉토리 정리 안 함).

    scope.py 도 사용 (purge_previous_history=True 시 옛/새 워크스페이스 양쪽 정리).
    """
    project_dir = encoded_project_dir(workspace_dir)
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
            purge_claude_history(workspace_dir)
            return 0, "no tmux session; history purged"
        return 0, "no-op (empty tmuxSession)"
    tty = _tmux_client_tty(tmux_session)
    tmux_kill_session(tmux_session)
    if tty:
        _close_terminal_tab_by_tty(tty)
    purged = False
    if workspace_dir and purge_history:
        purged = purge_claude_history(workspace_dir)
    log.info(
        "cleanup_agent: session=%s tty=%s purgeHistory=%s purged=%s",
        tmux_session, tty or "(none)", purge_history, purged,
    )
    return 0, "ok"
