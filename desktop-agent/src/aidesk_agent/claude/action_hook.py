"""Claude Code 의 PostToolUse 훅에 액션 로깅 스크립트를 자동 등록.

prompt_hook.py 와 같은 패턴이지만 별도 스크립트 (aidesk-action-hook.cjs) 로 분리 —
역할이 다름 (응답 대기 상태 마킹 vs mutation 감사 로그).

등록 매처:
  - Write|Edit|MultiEdit|NotebookEdit  (파일 변경)
  - Bash                                (일반 명령 실행)
  - mcp__postgres__.*                   (DB MCP)
  - mcp__jdbc-oracle__.*                (DB MCP)

기존 hooks 항목 (kaflix-hook, prompt-hook 등) 은 건드리지 않고 우리 명령만 머지/제거.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_HOME = Path(os.environ.get("HOME", "")) if os.environ.get("HOME") else Path.home()
SETTINGS_PATH = _HOME / ".claude" / "settings.json"
_SCRIPT_FILENAME = "aidesk-action-hook.cjs"
_SCRIPT_BASE_NAME = "aidesk-action-hook"

# 단일 PostToolUse 항목에서 매처 alternation 로 한 번에 잡음.
_FILE_MUTATION_MATCHER = "Write|Edit|MultiEdit|NotebookEdit"
_BASH_MATCHER = "Bash"
_DB_MCP_MATCHER = "mcp__postgres__.*|mcp__jdbc-oracle__.*|mcp__mysql__.*|mcp__sqlite__.*"

_HOOK_SPEC: list[tuple[str, str]] = [
    ("PostToolUse", _FILE_MUTATION_MATCHER),
    ("PostToolUse", _BASH_MATCHER),
    ("PostToolUse", _DB_MCP_MATCHER),
]


def _locate_script() -> Path | None:
    from .._shared import aidesk_hooks_dir  # noqa: PLC0415
    candidates = [
        aidesk_hooks_dir() / _SCRIPT_FILENAME,
        Path(__file__).resolve().parents[3] / "desktop-agent" / "scripts" / _SCRIPT_FILENAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _read_settings() -> dict:
    if not SETTINGS_PATH.exists() or SETTINGS_PATH.stat().st_size == 0:
        return {}
    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        log.warning("action-hook: read %s failed: %s", SETTINGS_PATH, e)
        return {}


def _ours_command(script_path: Path) -> str:
    return f'node "{script_path.resolve()}"'


def _is_ours(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    cmd = str(entry.get("command") or "")
    return _SCRIPT_BASE_NAME in cmd


def _strip_ours_from_block(block: dict) -> dict:
    inner = block.get("hooks") or []
    filtered = [h for h in inner if not _is_ours(h)]
    new_block = dict(block)
    new_block["hooks"] = filtered
    return new_block


def install_action_hooks() -> int:
    """`~/.claude/settings.json` 의 PostToolUse 에 우리 액션 훅 머지.

    @return 0 = ok, 1 = 스크립트 파일 미발견, 2 = settings.json 갱신 실패
    """
    script_path = _locate_script()
    if script_path is None:
        return 1
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        root = _read_settings()
        hooks_root = root.get("hooks")
        if not isinstance(hooks_root, dict):
            hooks_root = {}

        # 1) 우리 명령 모두 제거 (기존 잔재 청소)
        for event, blocks in list(hooks_root.items()):
            if not isinstance(blocks, list):
                continue
            cleaned: list[dict] = []
            for block in blocks:
                if not isinstance(block, dict):
                    cleaned.append(block)
                    continue
                stripped = _strip_ours_from_block(block)
                if stripped.get("hooks") or block.get("matcher") not in (None, ""):
                    cleaned.append(stripped)
            hooks_root[event] = [b for b in cleaned if (b.get("hooks") or b.get("matcher"))]

        # 2) 우리 spec 등록 — 각 매처별로 별도 block
        for event, matcher in _HOOK_SPEC:
            blocks = hooks_root.setdefault(event, [])
            blocks.append({
                "matcher": matcher,
                "hooks": [{"type": "command", "command": _ours_command(script_path)}],
            })

        root["hooks"] = hooks_root
        SETTINGS_PATH.write_text(
            json.dumps(root, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info("action-hook: installed at %s (%d matchers)", script_path, len(_HOOK_SPEC))
        return 0
    except OSError as e:
        log.warning("action-hook: install failed: %s", e)
        return 2


def _current_hooks_match_script() -> bool:
    target = _locate_script()
    if target is None:
        return False
    root = _read_settings()
    hooks_root = root.get("hooks")
    if not isinstance(hooks_root, dict):
        return False
    expected = str(target.resolve())
    count = 0
    for blocks in hooks_root.values():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for h in block.get("hooks") or []:
                if not _is_ours(h):
                    continue
                cmd = str(h.get("command") or "")
                if expected not in cmd:
                    return False
                count += 1
    return count >= len(_HOOK_SPEC)


def auto_install_on_startup() -> None:
    """Helper 시작 시 — 누락/마이그레이션 필요 시 재등록."""
    if _current_hooks_match_script():
        log.info("action-hook: already installed at current script path")
        return
    rc = install_action_hooks()
    if rc == 0:
        log.info("action-hook: installed/migrated — restart Claude Code to activate")
    else:
        log.warning("action-hook: auto-install failed rc=%s", rc)
