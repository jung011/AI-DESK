"""tmux 자동 설치 — macOS 의 helper startup 시 부재 감지 → brew install.

helper 의 핵심 기능 (web 터미널 / 외부 터미널 / agent attach 등) 이 tmux 의존.
신규 mac 사용자 가 helper .pkg install 후 *tmux 별도 설치 부담* 차단.

룰 ([[project-helper-multiplexer-bundling-followup]]):
- tmux 있음 (어떤 경로든) → skip. 사용자 환경 보존 (직접 빌드/port 사용자 침범 X)
- 없음 + brew 있음 → 자동 brew install (code-server 패턴 재사용)
- 없음 + brew 없음 → 로그 warning + 사용자 수동 설치 안내. helper 의 다른 기능은 정상

Windows 는 zellij — 별도 cycle (동료 작성 win-helper, 협의 필요).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import sys

log = logging.getLogger(__name__)

_BREW_INSTALL_TIMEOUT_SEC = 180.0  # tmux 첫 install 1~2분 가능 (libevent / ncurses dep)


async def _try_brew_install_tmux() -> str | None:
    """`brew install tmux` 비-인터랙티브. 성공 시 새 PATH 의 tmux 반환."""
    brew = shutil.which("brew")
    if not brew:
        log.warning(
            "tmux 미설치 + brew 도 없음 — helper 의 터미널 기능 비활성. "
            "수동 설치: https://brew.sh 후 `brew install tmux`"
        )
        return None
    log.info("tmux 자동 설치 시도: brew install tmux (1~2분 소요 가능)")
    try:
        proc = await asyncio.create_subprocess_exec(
            brew, "install", "tmux",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_BREW_INSTALL_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            proc.kill()
            log.warning("brew install tmux timeout — helper 터미널 기능 비활성")
            return None
        if proc.returncode != 0:
            tail = stdout.decode("utf-8", errors="replace")[-400:]
            log.warning("brew install tmux 실패 (rc=%s):\n%s", proc.returncode, tail)
            return None
        log.info("tmux 설치 완료")
        return shutil.which("tmux")
    except OSError as e:
        log.warning("brew install tmux 실행 실패: %s", e)
        return None


async def ensure_tmux_installed() -> str | None:
    """PATH 의 tmux 경로 반환. macOS 에서만 *부재 시* brew install 시도.

    linux/windows 는 *부재 시도 skip* — 패키지 매니저 가정 어렵고 helper .pkg
    환경 외에서 사용자 자체 install 가정.

    log path 별:
    - 있음 → "tmux already installed: <path>" (사용자가 skip 정상 작동 확인 가능)
    - 부재 + brew 있음 → "tmux 자동 설치 시도" → 성공 "tmux 설치 완료" or 실패 warning
    - 부재 + brew 없음 → "tmux 미설치 + brew 도 없음" warning
    """
    path = shutil.which("tmux")
    if path:
        log.info("tmux already installed: %s — skip auto-install", path)
        return path
    if sys.platform != "darwin":
        log.warning("tmux 미설치 (platform=%s). 사용자가 직접 설치 필요.", sys.platform)
        return None
    return await _try_brew_install_tmux()
