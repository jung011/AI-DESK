"""Helper 자가 진단 (self-heal).

좀비 상태 — process 는 살아있는데 backend SSE 가 끊긴 채로 reconnect 도 실패하는 상태 — 를
감지해서 자기 자살. macOS LaunchAgent 의 `KeepAlive=true` 가 자동 재기동.

좀비 vs 진짜 죽음:
- *진짜 죽음* (process 종료): LaunchAgent 가 인지 + 자동 재기동. watchdog 무관.
- *좀비* (process 살아있는데 SSE event 안 옴): LaunchAgent 모름. watchdog 이 self-kill 로
  재기동 트리거.

판정 기준:
backend 가 30초 주기로 SSE heartbeat (comment line) 를 보내므로 — backend 1.23+ —
어떤 SSE event 든 N초간 미수신이면 SSE 가 dead 라고 판정. sse_consumer 가 받는 모든 event
(heartbeat comment / message.deliver) 마다 `mark_sse_event()` 호출해 idle timer 갱신.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time

log = logging.getLogger(__name__)

# 마지막 SSE event 수신 시각 (monotonic). 초기값 = startup 시각 — 첫 SSE 연결 전에 watchdog
# 이 즉시 self-kill 하지 않게 buffer.
_last_sse_event_at = time.monotonic()

# 첫 SSE event 한 번이라도 받았는지. *Initial-bootstrap guard*:
# 환경 이슈로 SSE 연결 자체가 안 되는 mac 에서 무한 self-kill 반복으로 PyInstaller 의 _MEI
# 임시 폴더가 손상되는 사고를 방지 — 첫 event 받기 전엔 watchdog 가 self-kill 발동 안 함.
# *진짜 좀비* (한 번 정상 연결 후 끊김) 는 그대로 잡힘.
_seen_first_event = False

# 감지 임계 — backend SSE heartbeat 30s 주기 가정 + 일시 reconnect buffer.
# 90초 = heartbeat 3회 누락 = 명확한 dead.
DEAD_SSE_THRESHOLD_SEC = 90.0

# watchdog 폴링 주기.
WATCHDOG_INTERVAL_SEC = 30.0


def mark_sse_event() -> None:
    """sse_consumer 가 backend 로부터 어떤 event 든 받을 때 호출. idle timer 갱신."""
    global _last_sse_event_at, _seen_first_event
    _last_sse_event_at = time.monotonic()
    _seen_first_event = True


async def watchdog_loop() -> None:
    """SSE idle 이 너무 길면 process self-kill — LaunchAgent KeepAlive 가 자동 재기동.

    단 *첫 SSE event 한 번이라도 받기 전엔* self-kill 안 함 (initial-bootstrap guard).
    환경 이슈로 SSE 연결 자체가 안 되는 mac 에서는 watchdog 가 *조용히 대기* — process 는
    alive 유지되지만 동작 안 함. 사용자가 외부 진단/fix 가능. 무한 self-kill 로 인한 binary
    손상 방지.

    AIDESK_HELPER_NO_WATCHDOG=1 — dev 인스턴스 처럼 LaunchAgent 없이 직접 실행 시
    self-kill 하면 영구 종료. 이 env 박으면 watchdog loop 비활성 (return).
    """
    import os
    if os.environ.get("AIDESK_HELPER_NO_WATCHDOG", "").strip() in ("1", "true", "yes"):
        log.info("watchdog: disabled by AIDESK_HELPER_NO_WATCHDOG env — skip loop")
        return
    log.info("watchdog: starting (threshold=%.0fs, interval=%.0fs)",
             DEAD_SSE_THRESHOLD_SEC, WATCHDOG_INTERVAL_SEC)
    while True:
        try:
            await asyncio.sleep(WATCHDOG_INTERVAL_SEC)
        except asyncio.CancelledError:
            log.info("watchdog: cancelled — exiting cleanly")
            raise
        if not _seen_first_event:
            # 첫 SSE event 못 받은 상태 — 환경 이슈 가능성. self-kill 안 함.
            log.debug("watchdog: no SSE event seen yet — guard active (no self-kill)")
            continue
        idle = time.monotonic() - _last_sse_event_at
        if idle > DEAD_SSE_THRESHOLD_SEC:
            log.error(
                "watchdog: SSE idle %.0fs (>%.0fs threshold) — process self-kill so LaunchAgent restarts",
                idle, DEAD_SSE_THRESHOLD_SEC,
            )
            # sys.exit 으로 깨끗하게 종료 — atexit hook / aiohttp shutdown 정상 실행.
            sys.exit(1)
        log.debug("watchdog: SSE idle %.0fs (ok)", idle)
