"""helper-pkg 다운로드 — Spring HelperDownloadController 와 1:1.

image 안 /app/helper/AIDeskHelper-X.Y.Z-arm64.pkg 를 인증 후 서빙.
"""
import re
from pathlib import Path

VERSION_RE = re.compile(r"AIDeskHelper-([0-9]+(?:\.[0-9]+)+)")


def locate_pkg(helper_pkg_dir: str, os_kind: str = "mac") -> Path | None:
    """디렉토리에서 OS 에 맞는 helper 패키지 반환 (sorted 순). 없으면 None.

    - mac : *.pkg  (macOS .pkg installer)
    - win : *.exe  (Windows AIDeskHelper-Setup.exe — 자체추출 설치기)

    Spring 의 `Files.list(dir).filter(...).findFirst()` 와 동등.
    """
    p = Path(helper_pkg_dir)
    if not p.is_dir():
        return None
    pattern = "*.exe" if os_kind == "win" else "*.pkg"
    candidates = sorted(p.glob(pattern))
    return candidates[0] if candidates else None


def extract_version(filename: str) -> str:
    """파일명에서 X.Y.Z 추출. 못 찾으면 빈 문자열."""
    m = VERSION_RE.search(filename)
    return m.group(1) if m else ""
