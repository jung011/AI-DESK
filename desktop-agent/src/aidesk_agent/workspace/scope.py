"""(me) 워크스페이스 검증 + ~/.claude.json 의 projects entry 갱신.

자체 채널 모델 (2026-05~) 이후 케플릭스 의존 폐기. 이 모듈은:
  - workspace 디렉토리 존재 검증
  - ~/.claude.json 의 projects[<ws>] 에 hasTrustDialogAccepted=true 마킹
  - 워크스페이스 안 .claude/settings.local.json 에 aidesk-channel MCP 권한 미리 허용
  - purge_previous_history / me_tmux_session 옵션 처리

scope_workspace 는 backend(도커) 가 호출 — 호스트 파일시스템에 접근 가능한 Helper 가 담당.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import shutil
from pathlib import Path

from .cleanup import purge_claude_history, tmux_kill_session

log = logging.getLogger(__name__)

# (me) 워크스페이스에서 claude 가 매번 사용자 승인을 묻지 않도록 미리 허용해 둘 MCP 도구.
# settings.local.json 의 permissions.allow 에 자동 추가된다.
_DEFAULT_ALLOWED_TOOLS = (
    "mcp__aidesk-channel__send_to",
    "mcp__aidesk-channel__reply",
    "mcp__aidesk-channel__check_inbox",
    "mcp__aidesk-channel__list_agents",
)


def _ensure_workspace_allowed_tools(workspace_dir: str) -> None:
    """워크스페이스의 `.claude/settings.local.json` 에 우리 MCP 도구 권한을 누락 없이 등록.

    사용자가 (me) 워크스페이스로 명시 선택한 시점 = aidesk-channel MCP 도구 매번 승인
    다이얼로그가 뜨는 것을 방지하겠다는 동의로 간주. 기존 항목은 보존하고 누락된 도구만
    append (사용자가 직접 박은 Bash/Read 권한 등 안 건드림).
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
    """A2A 워크스페이스 검증 + `~/.claude.json` 의 projects 마킹.

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

    # 새 워크스페이스의 projects entry 에 hasTrustDialogAccepted=True 마킹.
    # 자체 채널 모델로 가면서 옛 kaflix-* 회수 / .mcp.json 작성 로직은 모두 폐기.
    # 우리 mcp 인 aidesk-channel 은 ~/.claude.json 의 글로벌 mcpServers 에 helper postinstall
    # 이 박아두므로 워크스페이스 자족 .mcp.json 이 따로 필요 없다.
    projects = root.setdefault("projects", {})
    new_entry = projects.setdefault(new_abs, {})
    new_entry["hasTrustDialogAccepted"] = True

    # atomic write — 임시 파일에 쓰고 rename
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
        "scope_workspace: %s → %s",
        old_workspace or "(none)",
        new_abs,
    )

    # 워크스페이스 안 .claude/settings.local.json 에 MCP 도구 권한 미리 등록.
    # (~/.claude.json 의 hasTrustDialogAccepted 와 별개. 도구별 사용 승인은 이 파일에 누적.)
    _ensure_workspace_allowed_tools(new_abs)

    if purge_previous_history:
        targets = {new_abs}
        if old_workspace and old_workspace.strip():
            targets.add(old_workspace)
        for t in targets:
            try:
                purge_claude_history(t)
            except OSError as e:
                log.warning("scope_workspace: purge failed for %s: %s", t, e)
        if me_tmux_session and me_tmux_session.strip():
            tmux_kill_session(me_tmux_session.strip())

    return 0, "", new_abs
