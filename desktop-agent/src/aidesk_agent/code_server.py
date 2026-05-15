"""code-server 라이프사이클 — Helper 가 spawn + 종료 시 정리.

- 시작 시 PATH 에 code-server 가 없으면 `brew install code-server` 로 자동 설치 시도.
- brew 도 없으면 경고만 남기고 임베드 VSCode 비활성으로 진행.
- spawn 옵션: `--auth=none --bind-addr=127.0.0.1:30082` (로컬 전용).
- Helper 종료 시 SIGTERM → 5초 후 미종료면 SIGKILL.
"""
from __future__ import annotations

import asyncio
import logging
import shutil

log = logging.getLogger(__name__)

DEFAULT_PORT = 30082
_BREW_INSTALL_TIMEOUT_SEC = 180.0  # brew 가 처음 받으면 1~2분 걸릴 수 있음


async def _try_brew_install() -> str | None:
    """`brew install code-server` 비-인터랙티브 실행. 성공 시 새 PATH 의 code-server 반환."""
    brew = shutil.which("brew")
    if not brew:
        log.warning(
            "code-server 미설치 + brew 도 없음 — 임베드 VSCode 비활성. "
            "수동 설치: https://code-server.dev/install.sh 또는 brew 먼저 설치"
        )
        return None
    log.info("code-server 자동 설치 시도: brew install code-server (1~2분 소요 가능)")
    try:
        proc = await asyncio.create_subprocess_exec(
            brew,
            "install",
            "code-server",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_BREW_INSTALL_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            proc.kill()
            log.warning("brew install timeout — 임베드 VSCode 비활성으로 진행")
            return None
        if proc.returncode != 0:
            tail = stdout.decode("utf-8", errors="replace")[-400:]
            log.warning("brew install 실패 (rc=%s):\n%s", proc.returncode, tail)
            return None
        log.info("code-server 설치 완료")
        return shutil.which("code-server")
    except OSError as e:
        log.warning("brew install 실행 실패: %s", e)
        return None


async def ensure_installed() -> str | None:
    """PATH 의 code-server 경로를 반환. 없으면 brew install 시도."""
    path = shutil.which("code-server")
    if path:
        return path
    return await _try_brew_install()


async def start_code_server(port: int = DEFAULT_PORT) -> asyncio.subprocess.Process | None:
    bin_path = await ensure_installed()
    if not bin_path:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            bin_path,
            "--auth=none",
            f"--bind-addr=127.0.0.1:{port}",
            "--disable-telemetry",
            "--disable-update-check",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        log.warning("code-server spawn 실패: %s", e)
        return None
    log.info("code-server spawned: pid=%s port=%s", proc.pid, port)
    return proc


async def stop_code_server(proc: asyncio.subprocess.Process | None) -> None:
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            log.warning("code-server SIGTERM 미응답 — SIGKILL")
            proc.kill()
            await proc.wait()
        log.info("code-server stopped (pid=%s)", proc.pid)
    except ProcessLookupError:
        pass
