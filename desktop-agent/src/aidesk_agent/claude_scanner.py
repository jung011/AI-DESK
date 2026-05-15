"""`~/.claude/projects/*` 디렉토리를 스캔해 워크스페이스별 최신 활동을 추출.

백엔드 `AgentStatusWatcher` 와 동일한 규칙으로 status (active/idle/done) 를
계산하므로 백엔드가 받아 t_ai_agent.workspace_dir 로 매칭할 때 호환된다.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# 백엔드 AgentStatusWatcher 와 같은 임계값.
ACTIVE_WINDOW_SEC = 120
IDLE_WINDOW_SEC = 30 * 60

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"

# 백엔드의 projectDirOf 와 동일한 escape 규칙 — 영숫자/언더스코어 외 모두 '-'.
_ESCAPE_RE = re.compile(r"[^A-Za-z0-9_]")

# 큰 jsonl 의 모든 라인을 파싱하는 비용 회피.
_MAX_LINES_FOR_CWD = 50


@dataclass
class WorkspaceInfo:
    encoded_dir: str
    workspace_dir: str | None
    latest_jsonl: str | None
    latest_mtime_iso: str | None
    age_sec: int | None
    status: str  # "active" | "idle" | "done" | "unknown"

    def as_dict(self) -> dict:
        return {
            "encodedDir": self.encoded_dir,
            "workspaceDir": self.workspace_dir,
            "latestJsonl": self.latest_jsonl,
            "latestMtime": self.latest_mtime_iso,
            "ageSec": self.age_sec,
            "status": self.status,
        }


def encode_workspace_dir(workspace_dir: str) -> str:
    """백엔드와 동일하게 workspace 경로 → 디렉토리명 escape."""
    return _ESCAPE_RE.sub("-", workspace_dir)


def estimate_status(age_sec: int | None) -> str:
    if age_sec is None:
        return "unknown"
    if age_sec <= ACTIVE_WINDOW_SEC:
        return "active"
    if age_sec <= IDLE_WINDOW_SEC:
        return "idle"
    return "done"


def _find_latest_jsonl(project_dir: Path, max_depth: int = 5) -> Path | None:
    latest: Path | None = None
    latest_mtime: float = -1.0
    base_depth = len(project_dir.parts)
    for root, _dirs, files in os.walk(project_dir):
        root_path = Path(root)
        if len(root_path.parts) - base_depth > max_depth:
            continue
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            p = root_path / name
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest = p
    return latest


def _extract_cwd(jsonl_path: Path) -> str | None:
    """jsonl 의 앞쪽 N줄에서 cwd 필드를 추출 (best-effort)."""
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fp:
            for idx, line in enumerate(fp):
                if idx >= _MAX_LINES_FOR_CWD:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("cwd"), str):
                    return obj["cwd"]
    except OSError:
        return None
    return None


def scan_workspaces() -> list[WorkspaceInfo]:
    if not CLAUDE_PROJECTS_ROOT.is_dir():
        return []
    results: list[WorkspaceInfo] = []
    now = datetime.now(timezone.utc).timestamp()
    for entry in sorted(CLAUDE_PROJECTS_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        latest = _find_latest_jsonl(entry)
        if latest is None:
            results.append(
                WorkspaceInfo(
                    encoded_dir=entry.name,
                    workspace_dir=None,
                    latest_jsonl=None,
                    latest_mtime_iso=None,
                    age_sec=None,
                    status="unknown",
                )
            )
            continue
        try:
            mtime = latest.stat().st_mtime
        except OSError:
            mtime = None
        age_sec = int(now - mtime) if mtime is not None else None
        latest_mtime_iso = (
            datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat() if mtime else None
        )
        cwd = _extract_cwd(latest)
        results.append(
            WorkspaceInfo(
                encoded_dir=entry.name,
                workspace_dir=cwd,
                latest_jsonl=str(latest),
                latest_mtime_iso=latest_mtime_iso,
                age_sec=age_sec,
                status=estimate_status(age_sec),
            )
        )
    return results
