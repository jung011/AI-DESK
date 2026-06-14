"""macOS 폴더/파일 선택 다이얼로그 — osascript choose folder / choose file."""
from __future__ import annotations

import subprocess


def browse_workspace() -> tuple[int, str]:
    """macOS 폴더 선택 다이얼로그. 사용자 취소시 빈 문자열 반환."""
    script = 'POSIX path of (choose folder with prompt "워크스페이스 폴더를 선택하세요")'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,  # 사용자가 다이얼로그 떠 있는 동안 충분히 대기
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return 4, f"폴더 다이얼로그 실행 실패: {e}"
    # 사용자 취소: returncode 1, stderr 에 -128
    if proc.returncode != 0:
        return 0, ""
    path = proc.stdout.strip()
    # POSIX path of 는 끝에 '/' 가 붙는 경우가 있어 정리
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return 0, path


def browse_file(prompt: str = "파일을 선택하세요") -> tuple[int, str]:
    """macOS 파일 선택 다이얼로그. 사용자 취소시 빈 문자열 반환."""
    # `choose file` 은 폴더가 아닌 파일을 고름. type filter 없이 모든 파일 허용.
    prompt_escaped = prompt.replace('"', '\\"')
    script = f'POSIX path of (choose file with prompt "{prompt_escaped}")'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return 4, f"파일 다이얼로그 실행 실패: {e}"
    if proc.returncode != 0:
        return 0, ""  # 사용자 취소
    return 0, proc.stdout.strip()
