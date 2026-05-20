"""(me) 워크스페이스 검증 + ~/.claude.json 의 kaflix-* MCP scope 이동.

kaflix-a2a / kaflix-channel MCP 서버는 (me) 가 지정한 A2A 워크스페이스에만 노출.
글로벌 mcpServers 의 두 항목을 새 워크스페이스 안 `.mcp.json` 으로 회수 (자족).

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

# 이동 대상 MCP 서버 이름
_SCOPED_MCP_SERVERS = ("kaflix-a2a", "kaflix-channel")

# 사내 도구 (kaflix) MCP 정의 영구 캐시 위치 — 한 번 회수해두면 워크스페이스 폴더 삭제,
# DB 초기화, 옛 워크스페이스 분실 등 어떤 케이스에도 정의 보존. 사용자가 사내 도구를
# 재실행해 글로벌 mcpServers 가 갱신되면 다음 scope_workspace 호출 시 캐시도 갱신.
_KAFLIX_MCP_CACHE = Path.home() / ".aidesk" / "kaflix-mcp.json"

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
                purge_claude_history(t)
            except OSError as e:
                log.warning("scope_workspace: purge failed for %s: %s", t, e)
        if me_tmux_session and me_tmux_session.strip():
            tmux_kill_session(me_tmux_session.strip())

    return 0, "", new_abs
