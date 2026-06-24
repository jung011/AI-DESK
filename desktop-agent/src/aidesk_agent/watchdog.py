"""Helper 자가 진단 (self-heal).

좀비 상태 — process 는 살아있는데 backend SSE 가 끊긴 채로 reconnect 도 실패하는 상태 — 를
감지해서 자기 자살. macOS LaunchAgent 의 `KeepAlive=true` 가 자동 재기동.

좀비 vs 진짜 죽음:
- *진짜 죽음* (process 종료): LaunchAgent 가 인지 + 자동 재기동. watchdog 무관.
- *좀비* (process 살아있는데 SSE event 안 옴): LaunchAgent 모름. watchdog 이 self-kill 로
  재기동 트리거.

두 종류 좀비:
1) *outbound 좀비* — backend SSE event 90s 미수신. mark_sse_event idle timer 로 감지.
2) *inbound 좀비* (helper 0.8.18 추가) — port 30083 listening 잃었거나 web server handler
   hang. 자기 /api/health 호출이 3회 연속 fail 시 self-kill. 2026-06-22 사고 = inbound
   좀비 패턴 (outbound 정상이지만 brower 가 helper 한테 접속 불가).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

import aiohttp

log = logging.getLogger(__name__)

# 마지막 SSE event 수신 시각 (monotonic). 초기값 = startup 시각 — 첫 SSE 연결 전에 watchdog
# 이 즉시 self-kill 하지 않게 buffer.
_last_sse_event_at = time.monotonic()

# 첫 SSE event 한 번이라도 받았는지. *Initial-bootstrap guard*:
# 환경 이슈로 SSE 연결 자체가 안 되는 mac 에서 무한 self-kill 반복으로 PyInstaller 의 _MEI
# 임시 폴더가 손상되는 사고를 방지 — 첫 event 받기 전엔 watchdog 가 self-kill 발동 안 함.
# *진짜 좀비* (한 번 정상 연결 후 끊김) 는 그대로 잡힘.
_seen_first_event = False

# self-ping 의 연속 실패 카운터. 3회 연속 fail (≈ 1.5min) 후 self-kill.
_self_ping_fail_count = 0

# self-ping 의 *최초 1회 성공* — web server bind 직후 self-kill 발동 X (initial-bootstrap guard).
_seen_self_ping_ok = False

# 감지 임계 — backend SSE heartbeat 30s 주기 가정 + 일시 reconnect buffer.
# 90초 = heartbeat 3회 누락 = 명확한 dead.
DEAD_SSE_THRESHOLD_SEC = 90.0

# self-ping 연속 실패 임계 — 3회 (≈ 1.5min) 후 self-kill.
SELF_PING_FAIL_THRESHOLD = 3

# watchdog 폴링 주기.
WATCHDOG_INTERVAL_SEC = 30.0


def mark_sse_event() -> None:
    """sse_consumer 가 backend 로부터 어떤 event 든 받을 때 호출. idle timer 갱신."""
    global _last_sse_event_at, _seen_first_event
    _last_sse_event_at = time.monotonic()
    _seen_first_event = True


async def _self_ping_ok() -> bool:
    """자기 /api/health 호출. inbound web server hang 감지."""
    port = os.environ.get("AIDESK_HELPER_PORT", "30083")
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        timeout = aiohttp.ClientTimeout(total=3.0)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                return r.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return False


async def watchdog_loop() -> None:
    """좀비 두 종류 감지 — process self-kill 시 LaunchAgent KeepAlive 가 자동 재기동.

    1) outbound 좀비: SSE idle > 90s
    2) inbound 좀비: self /api/health 3회 연속 fail

    둘 다 *initial-bootstrap guard* — 첫 정상 신호 수신 전에는 self-kill 안 함.
    환경 이슈로 helper 자체 미동작 mac 에서 무한 self-kill 반복으로 PyInstaller 의 _MEI
    임시 폴더 손상 방지.

    AIDESK_WATCHDOG_DISABLED=1 — dev / 검증 환경 우회용. LaunchAgent 가 없는 환경에선
    self-kill 후 자동 재기동이 없어 dev helper 죽음. 운영 .pkg 에선 절대 사용 X.
    """
    if os.environ.get("AIDESK_WATCHDOG_DISABLED") == "1":
        log.warning("watchdog: DISABLED via AIDESK_WATCHDOG_DISABLED=1 (dev mode)")
        return

    global _self_ping_fail_count, _seen_self_ping_ok
    log.info(
        "watchdog: starting (sse_threshold=%.0fs, self_ping_fails=%d, interval=%.0fs)",
        DEAD_SSE_THRESHOLD_SEC, SELF_PING_FAIL_THRESHOLD, WATCHDOG_INTERVAL_SEC,
    )
    while True:
        try:
            await asyncio.sleep(WATCHDOG_INTERVAL_SEC)
        except asyncio.CancelledError:
            log.info("watchdog: cancelled — exiting cleanly")
            raise

        # === 1) outbound 좀비 (SSE idle) — DISABLED ===
        # helper proxy (0.8.23+) 도입 후 backend 통신은 proxy ws 가 담당. SSE 는 *event
        # 발사 빈도* 가 사용자 mac 의 agent 활동에 따라 가변이라 idle = 정상 (사용자가
        # 자고 있을 때, agent 모두 비활성, helper 만 reporter 돌릴 때 등).
        # 0.8.24 의 min(sse,proxy) logic 도 *둘 다 event 없음* 케이스 false-positive
        # self-kill 사고. inbound self-ping (아래) 만으로 helper 자체 hang 감지 충분.
        # (자세한 회고: [[feedback-helper-watchdog-outbound-false-positive]])
        if _seen_first_event:
            sse_idle = time.monotonic() - _last_sse_event_at
            log.debug("watchdog: SSE idle %.0fs (outbound check disabled)", sse_idle)

        # === 2) inbound 좀비 (self /api/health) ===
        ok = await _self_ping_ok()
        if ok:
            if not _seen_self_ping_ok:
                log.info("watchdog: self-ping first OK — inbound guard activated")
                _seen_self_ping_ok = True
            if _self_ping_fail_count > 0:
                log.info("watchdog: self-ping recovered after %d fails", _self_ping_fail_count)
            _self_ping_fail_count = 0
            continue
        # fail
        if not _seen_self_ping_ok:
            # web server bind 전 — guard 활성 (initial-bootstrap)
            log.debug("watchdog: self-ping not yet OK — inbound guard active (no self-kill)")
            continue
        _self_ping_fail_count += 1
        log.warning(
            "watchdog: self-ping FAIL %d/%d (web server hang/unbound)",
            _self_ping_fail_count, SELF_PING_FAIL_THRESHOLD,
        )
        if _self_ping_fail_count >= SELF_PING_FAIL_THRESHOLD:
            log.error(
                "watchdog: self-ping %d 연속 fail — inbound 좀비 확정, process self-kill",
                _self_ping_fail_count,
            )
            sys.exit(1)
