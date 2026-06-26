"""Claude Code statusLine hook 관리 + 로컬 사용량 조회.

Spring Boot UsageService 의 Python 포트. 백엔드가 도커 컨테이너로 옮겨가면서
호스트의 `~/.claude/settings.json` 과 `~/.claude/aidesk-usage/*.json` 을 못 보게 됐기 때문에,
호스트에서 직접 도는 Helper 가 이 책임을 갖는다.

- 데이터 소스: `~/.claude/aidesk-usage/{sessionId}.json` — adesk-cli 의 statusline 스크립트가
  Claude Code 의 statusLine 콜백에서 받은 JSON (rate_limits, context_window) 을 기록한 파일.
- 5h rate-limit 은 모든 세션이 같은 글로벌 윈도우를 공유하므로 fiveHourResetsAt 이 미래인
  파일만 신뢰. 가장 최근 mtime 의 파일을 노출.
- 스크립트 미설치 시 ready=False — 프론트가 설치 안내 표시.
"""
from __future__ import annotations

import json
import logging
import os
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

_HOME = Path(os.environ.get("HOME", "")) if os.environ.get("HOME") else Path.home()
USAGE_DIR = _HOME / ".claude" / "aidesk-usage"
SETTINGS_PATH = _HOME / ".claude" / "settings.json"
_SCRIPT_BASE_NAME = "aidesk-statusline"  # OURS 판정용 — 옛 .js 도 우리것으로 인식해 마이그레이션 트리거
_SCRIPT_FILENAME = "aidesk-statusline.cjs"


class HookState(str, Enum):
    ABSENT = "absent"
    OURS = "ours"
    OTHER = "other"


def _locate_script() -> Path | None:
    """`aidesk-statusline.cjs` 의 절대 경로 반환.

    우선순위: pkg 설치본 (aidesk_share_dir/hooks) → 개발 모드 monorepo 경로.
    """
    from .._shared import aidesk_hooks_dir  # noqa: PLC0415
    candidates = [
        aidesk_hooks_dir() / _SCRIPT_FILENAME,
        Path(__file__).resolve().parents[3] / "adesk-cli" / "bin" / _SCRIPT_FILENAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _read_settings() -> dict | None:
    if not SETTINGS_PATH.exists() or SETTINGS_PATH.stat().st_size == 0:
        return None
    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as e:
        log.warning("usage: read %s failed: %s", SETTINGS_PATH, e)
        return None


def inspect_hook() -> HookState:
    root = _read_settings()
    if not root:
        return HookState.ABSENT
    status_line = root.get("statusLine")
    if not isinstance(status_line, dict):
        return HookState.ABSENT
    cmd = str(status_line.get("command") or "").strip()
    if not cmd:
        return HookState.ABSENT
    return HookState.OURS if _SCRIPT_BASE_NAME in cmd else HookState.OTHER


def _current_hook_matches_script() -> bool:
    """등록된 명령이 현재 locate_script() 와 정확히 같은 경로를 가리키는지."""
    target = _locate_script()
    if target is None:
        return False
    root = _read_settings()
    if not root:
        return False
    cmd = str(root.get("statusLine", {}).get("command") or "")
    return str(target.resolve()) in cmd


def install_statusline_hook() -> int:
    """`~/.claude/settings.json` 에 statusLine 블록을 주입 (이미 있으면 교체).

    @return 0 = ok, 1 = 스크립트 파일 미발견, 2 = settings.json 갱신 실패
    """
    script_path = _locate_script()
    if script_path is None:
        return 1
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        root = _read_settings() or {}
        root["statusLine"] = {
            "type": "command",
            "command": f'node "{script_path.resolve()}"',
        }
        SETTINGS_PATH.write_text(json.dumps(root, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("usage: installed statusLine hook at %s", script_path)
        return 0
    except OSError as e:
        log.warning("usage: install hook failed: %s", e)
        return 2


def auto_install_on_startup() -> None:
    """Helper 시작 시 한 번 — Spring 의 @PostConstruct 와 동등.

    다른 statusLine 명령이 점유 중이면 건드리지 않음. 옛 경로 (.js) 면 마이그레이션.
    """
    s = inspect_hook()
    if s == HookState.OTHER:
        log.info("usage: statusLine occupied by another command; skipping auto-install")
        return
    if s == HookState.OURS and _current_hook_matches_script():
        log.info("usage: statusLine already pointing to our current script")
        return
    rc = install_statusline_hook()
    if rc == 0:
        action = "path migrated" if s == HookState.OURS else "auto-installed"
        log.info("usage: statusLine %s — restart Claude Code to activate", action)
    else:
        log.warning("usage: statusLine auto-install failed rc=%s", rc)


def _belongs_to_current_window(file: Path, now_sec: int) -> bool:
    """fiveHourResetsAt 이 현재보다 미래인 파일만 현 윈도우에 속한 것으로 간주.

    다른 세션이 idle 해서 statusline 이 갱신 안 된 채 윈도우만 리셋되면 옛 사용률(예: 81%)을
    그대로 들고 있어 stale — 그런 파일은 제외.
    """
    try:
        with file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        resets_at = int(data.get("fiveHourResetsAt") or 0)
        return resets_at > now_sec
    except (OSError, json.JSONDecodeError, ValueError):
        return False


def _find_latest(dir_: Path) -> Path | None:
    if not dir_.is_dir():
        return None
    now_sec = int(__import__("time").time())
    candidates = []
    try:
        for p in dir_.iterdir():
            if p.is_file() and p.name.endswith(".json") and _belongs_to_current_window(p, now_sec):
                candidates.append(p)
    except OSError as e:
        log.warning("usage: list %s failed: %s", dir_, e)
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _as_int(node, default: int) -> int:
    if node is None:
        return default
    try:
        return int(round(float(node)))
    except (TypeError, ValueError):
        return default


def _as_long(node, default: int) -> int:
    if node is None:
        return default
    try:
        return int(node)
    except (TypeError, ValueError):
        return default


def get_local_usage() -> dict:
    """프론트 LocalUsageBar 에 그대로 전달되는 dict — 백엔드 LocalUsageRsVo 와 같은 키."""
    hook = inspect_hook()
    rs: dict = {
        "fiveHourPct": -1,
        "fiveHourResetsAt": 0,
        "weeklyPct": -1,
        "weeklyResetsAt": 0,
        "contextPct": -1,
        "source": "",
        "ready": False,
        "hookInstalled": hook == HookState.OURS,
        "hookOccupiedByOther": hook == HookState.OTHER,
    }

    latest = _find_latest(USAGE_DIR)
    if latest is None:
        return rs  # ready=False — statusLine 미가동 / stale

    try:
        with latest.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("usage: read %s failed: %s", latest, e)
        return rs

    rs["ready"] = True
    rs["source"] = str(latest)
    rs["fiveHourPct"] = _as_int(data.get("fiveHourUsedPct"), -1)
    rs["fiveHourResetsAt"] = _as_long(data.get("fiveHourResetsAt"), 0)
    rs["weeklyPct"] = _as_int(data.get("weeklyUsedPct"), -1)
    rs["weeklyResetsAt"] = _as_long(data.get("weeklyResetsAt"), 0)
    # contextRemainingPct 는 "남은 %" — 사용량으로 환산 (자동 압축 16.5% 마진은 무시).
    rem = _as_int(data.get("contextRemainingPct"), -1)
    if rem >= 0:
        rs["contextPct"] = max(0, min(100, 100 - rem))
    return rs
