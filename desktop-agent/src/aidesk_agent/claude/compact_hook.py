"""Claude Code 의 PreCompact / PostCompact hooks 자동 등록.

ctx 95% 도달 시 자동 compact 가 발동되면:
- PreCompact: backend status='compacting' set + "memory 정리해주세요" prompt inject
- PostCompact: 12초 후 status='idle' 복구 (frontend 폴링이 compacting 한 번이라도 catch 보장)

기존 prompt_hook 와 마찬가지로 settings.json 의 다른 hook 항목은 건드리지 않고
우리 명령만 merge/remove.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_HOME = Path(os.environ.get("HOME", "")) if os.environ.get("HOME") else Path.home()
SETTINGS_PATH = _HOME / ".claude" / "settings.json"
_SCRIPT_FILENAME = "aidesk-compact-hook.cjs"
_SCRIPT_BASE_NAME = "aidesk-compact-hook"

# 등록 spec — (event, mode) 쌍.
_HOOK_SPEC: list[tuple[str, str]] = [
    ("PreCompact", "pre"),
    ("PostCompact", "post"),
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
        log.warning("compact-hook: read %s failed: %s", SETTINGS_PATH, e)
        return {}


def _ours_command(script_path: Path, mode: str) -> str:
    return f'node "{script_path.resolve()}" {mode}'


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


def install_compact_hooks() -> int:
    """settings.json 의 PreCompact/PostCompact 에 우리 hook merge.

    @return 0 = ok, 1 = 스크립트 미발견, 2 = 갱신 실패
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

        # 1) PreCompact / PostCompact event 의 모든 block 에서 우리 명령 제거 (마이그레이션)
        for event in ("PreCompact", "PostCompact"):
            blocks = hooks_root.get(event)
            if not isinstance(blocks, list):
                continue
            cleaned: list[dict] = []
            for block in blocks:
                if not isinstance(block, dict):
                    cleaned.append(block)
                    continue
                stripped = _strip_ours_from_block(block)
                if stripped.get("hooks"):
                    cleaned.append(stripped)
            hooks_root[event] = cleaned

        # 2) 우리 spec 새로 등록
        for event, mode in _HOOK_SPEC:
            blocks = hooks_root.setdefault(event, [])
            blocks.append({
                "hooks": [{"type": "command", "command": _ours_command(script_path, mode)}],
            })

        root["hooks"] = hooks_root
        SETTINGS_PATH.write_text(
            json.dumps(root, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info("compact-hook: installed at %s", script_path)
        return 0
    except OSError as e:
        log.warning("compact-hook: install failed: %s", e)
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
    counts = {"pre": 0, "post": 0}
    for event in ("PreCompact", "PostCompact"):
        blocks = hooks_root.get(event) or []
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
                if cmd.endswith(" pre"):
                    counts["pre"] += 1
                elif cmd.endswith(" post"):
                    counts["post"] += 1
    return counts["pre"] >= 1 and counts["post"] >= 1


def auto_install_on_startup() -> None:
    """Helper 시작 시 한 번 — 누락/마이그레이션 필요 시 재등록."""
    if _current_hooks_match_script():
        log.info("compact-hook: already installed at current script path")
        return
    rc = install_compact_hooks()
    if rc == 0:
        log.info("compact-hook: installed/migrated — restart Claude Code to activate")
    else:
        log.warning("compact-hook: auto-install failed rc=%s", rc)
