"""로컬 tmux 세션 목록 조회. tmux 미설치 / 서버 미가동 시 빈 리스트."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class TmuxSessionInfo:
    name: str
    attached: bool
    windows: int

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "attached": self.attached,
            "windows": self.windows,
        }


def _tmux_available() -> bool:
    return shutil.which("tmux") is not None


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
    results: list[TmuxSessionInfo] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, attached, windows = parts[0], parts[1], parts[2]
        try:
            results.append(
                TmuxSessionInfo(
                    name=name,
                    attached=attached != "0",
                    windows=int(windows),
                )
            )
        except ValueError:
            continue
    return results
