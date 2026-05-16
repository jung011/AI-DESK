"""Claude Code 의 hooks 섹션에 "응답 대기" 감지 훅을 자동 등록.

claude 가 사용자 입력을 기다리는 순간 (AskUserQuestion / ExitPlanMode / 권한 승인 Notification)
마커 파일을 생성하고, 입력 완료 / 답변 후 / 턴 종료 시점 (PostToolUse / Stop / UserPromptSubmit)
에 마커를 지운다. 마커는 `~/.claude/aidesk-prompt/{sessionId}.json` 에 저장되고,
`claude_scanner` 가 이걸 확인해 status="waiting" 으로 격상시킨다.

기존 hooks 항목 (예: kaflix-hook 의 Stop) 은 건드리지 않고 우리 명령만 머지/제거 한다.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_HOME = Path(os.environ.get("HOME", "")) if os.environ.get("HOME") else Path.home()
SETTINGS_PATH = _HOME / ".claude" / "settings.json"
_SCRIPT_FILENAME = "aidesk-prompt-hook.cjs"
_SCRIPT_BASE_NAME = "aidesk-prompt-hook"  # OURS 판정용
_MARK_TOOL_MATCHER = "AskUserQuestion|ExitPlanMode"

# 등록 대상 (event, matcher, mode) — Claude Code hooks 구조에 맞춰 정의.
# matcher 가 None 이면 모든 트리거에 매칭 (Notification / Stop / UserPromptSubmit 등).
_HOOK_SPEC: list[tuple[str, str | None, str]] = [
    # AI 가 응답을 기다리기 시작 → mark
    ("PreToolUse", _MARK_TOOL_MATCHER, "mark"),
    ("Notification", None, "mark"),
    # 답변 받음 / 턴 종료 → clear (Stop 은 안전망 — 누락된 clear 흡수)
    ("PostToolUse", _MARK_TOOL_MATCHER, "clear"),
    ("UserPromptSubmit", None, "clear"),
    ("Stop", None, "clear"),
]


def _locate_script() -> Path | None:
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "desktop-agent" / "scripts" / _SCRIPT_FILENAME
    return candidate if candidate.is_file() else None


def _read_settings() -> dict:
    if not SETTINGS_PATH.exists() or SETTINGS_PATH.stat().st_size == 0:
        return {}
    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        log.warning("prompt-hook: read %s failed: %s", SETTINGS_PATH, e)
        return {}


def _ours_command(script_path: Path, mode: str) -> str:
    return f'node "{script_path.resolve()}" {mode}'


def _is_ours(entry: dict) -> bool:
    """hooks[].hooks[] 항목 중 우리 스크립트를 가리키는지."""
    if not isinstance(entry, dict):
        return False
    cmd = str(entry.get("command") or "")
    return _SCRIPT_BASE_NAME in cmd


def _strip_ours_from_block(block: dict) -> dict:
    """hooks[] 안의 단일 block 에서 우리 명령만 제거한 사본 반환."""
    inner = block.get("hooks") or []
    filtered = [h for h in inner if not _is_ours(h)]
    new_block = dict(block)
    new_block["hooks"] = filtered
    return new_block


def install_prompt_hooks() -> int:
    """`~/.claude/settings.json` 의 hooks 섹션에 우리 훅을 머지.

    이미 등록된 우리 명령은 모두 제거 후 현재 경로로 재등록 (마이그레이션 안전).
    기존의 사용자 / kaflix 훅은 건드리지 않는다.

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

        # 1) 모든 이벤트의 모든 block 에서 우리 명령 제거 (기존 잔재 청소)
        for event, blocks in list(hooks_root.items()):
            if not isinstance(blocks, list):
                continue
            cleaned_blocks: list[dict] = []
            for block in blocks:
                if not isinstance(block, dict):
                    cleaned_blocks.append(block)
                    continue
                stripped = _strip_ours_from_block(block)
                # 우리 명령만 들어있던 block 은 비었으면 통째로 제거 (단, 다른 명령 있으면 보존)
                if stripped.get("hooks") or block.get("matcher") not in (None, ""):
                    cleaned_blocks.append(stripped)
            hooks_root[event] = [b for b in cleaned_blocks if (b.get("hooks") or b.get("matcher"))]

        # 2) 우리 spec 을 새로 등록 — 매처별로 별도 block 으로 추가
        for event, matcher, mode in _HOOK_SPEC:
            blocks = hooks_root.setdefault(event, [])
            new_block: dict = {
                "hooks": [{"type": "command", "command": _ours_command(script_path, mode)}],
            }
            if matcher is not None:
                new_block["matcher"] = matcher
            blocks.append(new_block)

        root["hooks"] = hooks_root
        SETTINGS_PATH.write_text(
            json.dumps(root, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info("prompt-hook: installed at %s", script_path)
        return 0
    except OSError as e:
        log.warning("prompt-hook: install failed: %s", e)
        return 2


def _current_hooks_match_script() -> bool:
    """등록된 우리 명령 5개가 모두 현재 경로를 가리키는지 (마이그레이션 필요 여부 판정)."""
    target = _locate_script()
    if target is None:
        return False
    root = _read_settings()
    hooks_root = root.get("hooks")
    if not isinstance(hooks_root, dict):
        return False
    expected = str(target.resolve())
    counts = {"mark": 0, "clear": 0, "stop": 0}
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
                if cmd.endswith(" mark"):
                    counts["mark"] += 1
                elif cmd.endswith(" clear"):
                    counts["clear"] += 1
                elif cmd.endswith(" stop"):
                    counts["stop"] += 1
    # 현재 spec: mark 2개 (PreToolUse + Notification) + clear 3개 (PostToolUse + UserPromptSubmit + Stop)
    # stop 모드는 더 이상 사용 안 함 — 발견되면 마이그레이션 (re-install) 필요.
    return counts["mark"] >= 2 and counts["clear"] >= 3 and counts["stop"] == 0


def auto_install_on_startup() -> None:
    """Helper 시작 시 한 번 — 누락/마이그레이션 필요 시 재등록."""
    if _current_hooks_match_script():
        log.info("prompt-hook: already installed at current script path")
        return
    rc = install_prompt_hooks()
    if rc == 0:
        log.info("prompt-hook: installed/migrated — restart Claude Code to activate")
    else:
        log.warning("prompt-hook: auto-install failed rc=%s", rc)
