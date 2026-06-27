"""로컬 tmux 세션 목록 조회. tmux 미설치 / 서버 미가동 시 빈 리스트.

session 별 *claude process tree 살아있는지* 검사 — backend 가 agent 의 tmux_session
매칭 시 *claude_alive=false 면 status='offline' 강제*. 사용자가 claude 종료해도
zsh prompt 만 남으면 옛 backend 가 idle 유지 사고 차단.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class TmuxSessionInfo:
    name: str
    attached: bool
    windows: int
    # session 의 어떤 pane 의 자식 process tree 에 claude 살아있는지. False = claude 종료됨.
    claude_alive: bool = False
    # helper 0.8.69+ — claude TUI 의 yes/no option dialog 검출 결과.
    # None = dialog 없음, dict = {"options": [{"index": 1, "label": "Yes"}, ...]}.
    prompt_dialog: dict | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "attached": self.attached,
            "windows": self.windows,
            "claudeAlive": self.claude_alive,
            "promptDialog": self.prompt_dialog,
        }


def _tmux_available() -> bool:
    return shutil.which("tmux") is not None


def _build_ps_tree() -> dict[int, list[tuple[int, str]]]:
    """ps -eo pid,ppid,comm 의 결과를 ppid → [(pid, comm)] dict 로. 1회만 호출 (N session 공유)."""
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid,ppid,comm"],
            capture_output=True, text=True, timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return {}
    children: dict[int, list[tuple[int, str]]] = {}
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append((pid, parts[2]))
    return children


def _tree_contains_claude(root_pid: int, children: dict[int, list[tuple[int, str]]]) -> bool:
    """root_pid 의 자식 tree 안에 claude process 있는지. claude code = node binary 라
    comm 이 'node' 또는 'claude' — 둘 다 매칭. BFS."""
    queue = [root_pid]
    seen = {root_pid}
    while queue:
        cur = queue.pop()
        for pid, comm in children.get(cur, []):
            if pid in seen:
                continue
            seen.add(pid)
            cn = comm.rsplit("/", 1)[-1].lower()  # absolute path → basename
            if "claude" in cn or cn == "node":
                return True
            queue.append(pid)
    return False


def _session_has_claude(session_name: str, ps_tree: dict[int, list[tuple[int, str]]]) -> bool:
    """tmux session 의 *어떤 pane* 의 자식 tree 에 claude 있는지."""
    try:
        proc = subprocess.run(
            ["tmux", "list-panes", "-t", session_name, "-a", "-F", "#{session_name}\t#{pane_pid}"],
            capture_output=True, text=True, timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if proc.returncode != 0:
        return False
    pane_pids: list[int] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or parts[0] != session_name:
            continue
        try:
            pane_pids.append(int(parts[1]))
        except ValueError:
            continue
    return any(_tree_contains_claude(pid, ps_tree) for pid in pane_pids)


def scan_sessions() -> list[TmuxSessionInfo]:
    if not _tmux_available():
        return []
    # 포맷: name:attached:windows
    fmt = "#{session_name}\t#{session_attached}\t#{session_windows}"
    try:
        proc = subprocess.run(
            ["tmux", "list-sessions", "-F", fmt],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    # exit code 1 + "no server running" 은 정상 — 빈 리스트 반환.
    if proc.returncode != 0:
        return []
    # ps tree 한 번 만 build — N session 의 claude detection 에 공유.
    ps_tree = _build_ps_tree()
    # prompt_dialog detection — claude alive 인 session 만 capture-pane 시도 (cost 절약).
    from .prompt_detector import detect_prompt_dialog
    results: list[TmuxSessionInfo] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, attached, windows = parts[0], parts[1], parts[2]
        try:
            alive = _session_has_claude(name, ps_tree) if ps_tree else False
            results.append(
                TmuxSessionInfo(
                    name=name,
                    attached=attached != "0",
                    windows=int(windows),
                    claude_alive=alive,
                    prompt_dialog=detect_prompt_dialog(name) if alive else None,
                )
            )
        except ValueError:
            continue
    return results
