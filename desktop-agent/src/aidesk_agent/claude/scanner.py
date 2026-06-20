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
# 응답 대기 마커가 이 시간을 넘기면 stale 로 간주 (hook 의 clear 가 실패한 케이스 대비).
WAITING_MARKER_TTL_SEC = 60 * 60

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
PROMPT_MARKER_DIR = Path.home() / ".claude" / "aidesk-prompt"

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
    context_pct: int | None = None  # aidesk-usage 의 cwd 매칭으로 추출

    def as_dict(self) -> dict:
        return {
            "encodedDir": self.encoded_dir,
            "workspaceDir": self.workspace_dir,
            "latestJsonl": self.latest_jsonl,
            "latestMtime": self.latest_mtime_iso,
            "ageSec": self.age_sec,
            "status": self.status,
            "contextPct": self.context_pct,
        }


def encode_workspace_dir(workspace_dir: str) -> str:
    """백엔드와 동일하게 workspace 경로 → 디렉토리명 escape."""
    return _ESCAPE_RE.sub("-", workspace_dir)


def estimate_status(age_sec: int | None) -> str:
    if age_sec is None:
        return "unknown"
    if age_sec <= ACTIVE_WINDOW_SEC:
        return "active"
    # IDLE_WINDOW_SEC 초과해도 동일하게 idle — 별도 'done' 상태 없음.
    # 30분+ 침묵은 그냥 오래 idle 한 거고 인스턴스 자체는 여전히 살아있다.
    return "idle"


def _has_fresh_prompt_marker(jsonl_path: Path, now_sec: float) -> bool:
    """jsonl 파일명의 sessionId 로 ~/.claude/aidesk-prompt/{sessionId}.json 존재 + 신선도 확인.

    파일이 있어도 WAITING_MARKER_TTL_SEC 이상 오래됐으면 stale 로 간주 (hook clear 누락 대비).
    """
    if not PROMPT_MARKER_DIR.is_dir():
        return False
    session_id = jsonl_path.stem  # "{uuid}.jsonl" → "{uuid}"
    marker = PROMPT_MARKER_DIR / f"{session_id}.json"
    try:
        st = marker.stat()
    except OSError:
        return False
    if now_sec - st.st_mtime > WAITING_MARKER_TTL_SEC:
        return False
    return True


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


def _load_cwd_to_context_pct() -> dict[str, int]:
    """`~/.claude/aidesk-usage/{sessionId}.json` 파일들을 읽어 cwd → context_pct dict 반환.

    같은 cwd 에 여러 session 파일이 있으면 *가장 최근 mtime* 의 값을 사용.
    statusline 의 record.cwd 가 *해당 claude code session 의 working dir* — agent 의
    workspace_dir 와 매칭됨.
    """
    usage_dir = Path.home() / ".claude" / "aidesk-usage"
    if not usage_dir.is_dir():
        return {}
    out: dict[str, tuple[float, int]] = {}  # cwd → (mtime, context_pct)
    for p in usage_dir.iterdir():
        if not p.is_file() or not p.suffix == ".json":
            continue
        try:
            mtime = p.stat().st_mtime
            with p.open("r", encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        cwd = rec.get("cwd")
        rem = rec.get("contextRemainingPct")
        if not cwd or rem is None:
            continue
        ctx_pct = max(0, min(100, 100 - int(rem)))
        prev = out.get(cwd)
        if prev is None or mtime > prev[0]:
            out[cwd] = (mtime, ctx_pct)
    return {cwd: v[1] for cwd, v in out.items()}


def scan_workspaces() -> list[WorkspaceInfo]:
    if not CLAUDE_PROJECTS_ROOT.is_dir():
        return []
    cwd_to_ctx = _load_cwd_to_context_pct()
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
        # 마커가 있으면 active/idle 보다 우선 — 사용자가 즉시 인지해야 할 상태.
        # done(30분+ 침묵) 까지 갔으면 사용자가 자리 비운 것이라 굳이 waiting 으로 격상 안 함.
        base_status = estimate_status(age_sec)
        if base_status in ("active", "idle") and _has_fresh_prompt_marker(latest, now):
            base_status = "waiting"
        results.append(
            WorkspaceInfo(
                encoded_dir=entry.name,
                workspace_dir=cwd,
                latest_jsonl=str(latest),
                latest_mtime_iso=latest_mtime_iso,
                age_sec=age_sec,
                status=base_status,
                context_pct=cwd_to_ctx.get(cwd) if cwd else None,
            )
        )
    return results
