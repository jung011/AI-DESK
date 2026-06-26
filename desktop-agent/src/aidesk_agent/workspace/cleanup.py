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


def _remove_mcp_entry(workspace_dir: str) -> bool:
    """`~/.claude.json` 의 `projects[workspace_dir].mcpServers["aidesk-channel"]` 삭제.

    그대로 두면 같은 workspace 로 *재생성 시* 옛 agent_id env 박힌 mcp 가 *deleted*
    backend agent_id 로 reconnect 시도 → 401 → 옛 token daemon storm 패턴.
    """
    if not workspace_dir:
        return False
    import json
    from pathlib import Path
    cj = Path.home() / ".claude.json"
    if not cj.is_file():
        return False
    try:
        data = json.loads(cj.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning("cleanup: ~/.claude.json read failed: %s", e)
        return False
    projects = data.get("projects", {})
    proj = projects.get(workspace_dir)
    if not isinstance(proj, dict):
        return False
    servers = proj.get("mcpServers", {})
    if not isinstance(servers, dict) or "aidesk-channel" not in servers:
        return False
    del servers["aidesk-channel"]
    try:
        cj.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        log.info("cleanup: removed mcp entry from ~/.claude.json projects.%s", workspace_dir)
        return True
    except OSError as e:
        log.warning("cleanup: ~/.claude.json write failed: %s", e)
        return False


def _kill_orphan_bot_adapter(agent_id: str) -> None:
    """agent_id 박힌 옛 bot-adapter process kill — Phase 5 후 spawn 안 하지만 옛 잔재."""
    if not agent_id:
        return
    try:
        subprocess.run(
            ["pkill", "-f", f"AIDESK_AGENT_ID={agent_id}"],
            capture_output=True, timeout=3, check=False,
        )
        log.info("cleanup: pkill -f AIDESK_AGENT_ID=%s", agent_id)
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning("cleanup: pkill bot-adapter failed: %s", e)


def cleanup_agent(
    tmux_session: str,
    workspace_dir: str | None = None,
    purge_history: bool = False,
    agent_id: str | None = None,
) -> tuple[int, str]:
    """에이전트 삭제 시 호출 — 사용자 mac 의 모든 잔재 정리.

    1) tmux session kill — claude TUI + mcp(bun) daemon 도 child 라 같이 죽음
    2) attached Terminal.app 윈도우 close (tty 매칭)
    3) `~/.claude.json` 의 projects[workspace_dir].mcpServers["aidesk-channel"] entry
       삭제 — 옛 token daemon storm 차단
    4) agent_id 박힌 옛 bot-adapter process pkill (잔재)
    5) purge_history=True + workspace_dir 면 `~/.claude/projects/{escaped}/` 의
       jsonl 까지 삭제 (재생성 시 `claude -c` 옛 대화 부활 차단)

    실패해도 backend DB 삭제 자체엔 영향 없도록 비-치명적으로 처리.
    """
    tty = _tmux_client_tty(tmux_session) if tmux_session else ""
    if tmux_session:
        tmux_kill_session(tmux_session)
        if tty:
            _close_terminal_tab_by_tty(tty)

    mcp_removed = _remove_mcp_entry(workspace_dir) if workspace_dir else False
    _kill_orphan_bot_adapter(agent_id) if agent_id else None

    purged = False
    if workspace_dir and purge_history:
        purged = purge_claude_history(workspace_dir)

    log.info(
        "cleanup_agent: session=%s tty=%s mcp_removed=%s bot_killed=%s purgeHistory=%s purged=%s",
        tmux_session or "(none)", tty or "(none)", mcp_removed,
        bool(agent_id), purge_history, purged,
    )
    return 0, "ok"
