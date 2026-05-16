"""신규 에이전트 부트스트랩 — 사용자가 터미널을 안 열어도 즉시 통신 가능하게.

두 가지를 처리:
  1) {workspaceDir}/.claude/settings.local.json 에 aidesk-channel MCP 권한 미리 부여
     → claude 시작 시 "Always allow" 프롬프트 자체가 안 뜸.
  2) `tmux new-session -d` 로 백그라운드 세션 시작 + claude 띄움
     → TmuxLastMileAdapter 의 last-mile delivery 가 바로 도달 가능.

Helper 가 호스트 사용자 권한으로 도니까 ~/.claude/* 및 사용자 워크스페이스에 자유롭게 쓸 수 있다.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .os_bridge import _has_past_session

log = logging.getLogger(__name__)

# Claude Code 가 워크스페이스 단위 trust 결정을 저장하는 글로벌 파일.
# projects[workspace_path] 객체에 hasTrustDialogAccepted=true 를 박아두면
# "trust this folder?" 첫 진입 프롬프트가 안 뜬다.
_CLAUDE_JSON_PATH = Path.home() / ".claude.json"

# 신규 AI 가 사내 협업 (aidesk-channel) 을 즉시 쓸 수 있게 하는 최소 권한 집합.
# 사용자가 추가로 도구 (Bash, Read 등) 를 쓰려면 그때 "Always allow" 로 누적된다.
DEFAULT_ALLOW = (
    "mcp__aidesk-channel__list_agents",
    "mcp__aidesk-channel__send_to",
    "mcp__aidesk-channel__reply",
    "mcp__aidesk-channel__check_inbox",
)


def _write_default_permissions(workspace_dir: str) -> tuple[bool, int]:
    """워크스페이스의 .claude/settings.local.json 에 DEFAULT_ALLOW 를 멱등하게 주입.

    Returns (ok, added_count). 기존 파일이 있어도 우리 키만 추가하고 사용자가 누적한
    다른 도구 권한은 보존한다.
    """
    ws = Path(workspace_dir).expanduser()
    try:
        ws.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("bootstrap: workspace mkdir failed ws=%s err=%s", workspace_dir, e)
        return False, 0

    settings_path = ws / ".claude" / "settings.local.json"
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("bootstrap: .claude mkdir failed ws=%s err=%s", workspace_dir, e)
        return False, 0

    data: dict = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError) as e:
            log.warning("bootstrap: settings read failed (will overwrite) path=%s err=%s",
                        settings_path, e)
            data = {}

    if not isinstance(data, dict):
        data = {}
    perms = data.setdefault("permissions", {})
    if not isinstance(perms, dict):
        perms = data["permissions"] = {}
    allow = perms.setdefault("allow", [])
    if not isinstance(allow, list):
        allow = perms["allow"] = []

    added = 0
    for tool in DEFAULT_ALLOW:
        if tool not in allow:
            allow.append(tool)
            added += 1

    if added > 0:
        try:
            settings_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            log.warning("bootstrap: settings write failed path=%s err=%s", settings_path, e)
            return False, 0

    log.info("bootstrap: permissions ws=%s added=%d total=%d", workspace_dir, added, len(allow))
    return True, added


def _mark_folder_trusted(workspace_dir: str) -> bool:
    """`~/.claude.json` 의 projects[workspaceDir] 에 hasTrustDialogAccepted=true 를 박는다.

    이 파일은 모든 워크스페이스의 상태가 누적되어 있으므로 atomic read-modify-write 로
    처리. 같은 파일에 동시 접근이 있어도 우리 키만 안전하게 교체된다.
    """
    if not _CLAUDE_JSON_PATH.exists():
        # claude 가 한 번도 안 떴으면 파일 자체가 없음 — 새로 만들기.
        try:
            _CLAUDE_JSON_PATH.write_text("{}\n", encoding="utf-8")
        except OSError as e:
            log.warning("bootstrap: ~/.claude.json create failed err=%s", e)
            return False

    try:
        raw = _CLAUDE_JSON_PATH.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError) as e:
        log.warning("bootstrap: ~/.claude.json read failed err=%s", e)
        return False

    if not isinstance(data, dict):
        data = {}
    projects = data.setdefault("projects", {})
    if not isinstance(projects, dict):
        projects = data["projects"] = {}

    entry = projects.setdefault(workspace_dir, {})
    if not isinstance(entry, dict):
        entry = projects[workspace_dir] = {}

    # 기존 키는 보존, trust 관련 3개만 명시.
    entry["hasTrustDialogAccepted"] = True
    # CLAUDE.md 가 외부 include 를 가지고 있어도 경고 안 띄움 — 신규 AI 부팅 streamline.
    entry.setdefault("hasClaudeMdExternalIncludesApproved", True)
    entry.setdefault("hasClaudeMdExternalIncludesWarningShown", True)

    # atomic write — 큰 누적 파일이라 중간에 깨지면 다른 워크스페이스도 영향.
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".claude.json.", dir=str(_CLAUDE_JSON_PATH.parent),
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, _CLAUDE_JSON_PATH)
    except OSError as e:
        log.warning("bootstrap: ~/.claude.json write failed err=%s", e)
        return False

    log.info("bootstrap: trust marker set ws=%s", workspace_dir)
    return True


def _start_tmux_detached(tmux_session: str, workspace_dir: str) -> bool:
    """tmux 세션을 detached 로 띄우고 안에서 claude 를 실행. 이미 있으면 그대로 둠."""
    # 이미 있으면 그대로 (idempotent — 같은 AI 재생성 시 무동작)
    check = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session],
        capture_output=True,
    )
    if check.returncode == 0:
        log.info("bootstrap: tmux already exists session=%s — skipping start", tmux_session)
        return True

    # 신규 AI 라도 사용자가 같은 워크스페이스로 재생성하는 케이스가 있을 수 있어 jsonl 체크.
    claude_cmd = "claude -c" if _has_past_session(workspace_dir) else "claude"

    # tmux new-session -d  → detached (사용자 화면에 안 뜸)
    # -A 와 함께 쓰면 안 됨 (-A 는 attach 의도) — -d 만 쓰면 새로 만들고 안 붙음
    try:
        subprocess.run(
            [
                "tmux", "new-session", "-d", "-s", tmux_session,
                "-c", workspace_dir,
                claude_cmd,
            ],
            check=True,
            capture_output=True,
        )
        log.info("bootstrap: tmux started detached ws=%s session=%s cmd=%s",
                 workspace_dir, tmux_session, claude_cmd)
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", "replace") if e.stderr else ""
        log.warning("bootstrap: tmux start failed session=%s err=%s", tmux_session, stderr)
        return False


def bootstrap_agent(workspace_dir: str, tmux_session: str) -> dict:
    """엔드포인트 본체. trust + 권한 + tmux 세 가지 모두 시도하고 결과 dict 반환.

    순서가 중요: trust 마커가 tmux 시작 전에 박혀야 claude 첫 부팅 때 프롬프트가 안 뜬다.
    """
    trust_ok = _mark_folder_trusted(workspace_dir)
    perms_ok, perms_added = _write_default_permissions(workspace_dir)
    tmux_ok = _start_tmux_detached(tmux_session, workspace_dir)
    return {
        "trustMarked": trust_ok,
        "permissionsWritten": perms_ok,
        "permissionsAdded": perms_added,
        "tmuxStarted": tmux_ok,
    }
