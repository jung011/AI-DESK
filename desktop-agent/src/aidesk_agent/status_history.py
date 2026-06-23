"""시스템 상태 시계열 sampler — uptimeSeconds + staleDaemonCount 의 24h history.

resource-cleanup 페이지의 시간 추이 그래프 데이터 source. helper restart 시
history 초기화 (in-memory ring buffer, 디스크 적재 X — 단순함 우선).

샘플링 주기 60s × 24h = 1440 entries. 각 entry = (timestamp, uptimeSeconds,
staleDaemonCount). 메모리 부담 매우 작음 (~50KB).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Deque

from . import cleanup as cleanup_mod

log = logging.getLogger(__name__)

SAMPLE_INTERVAL_SEC = 60.0  # 1분 마다 sampling
HISTORY_MAX_ENTRIES = 24 * 60  # 24h × 60min = 1440 entries

# (timestamp_ms, uptimeSeconds | None, staleDaemonCount)
_history: Deque[tuple[int, float | None, int]] = deque(maxlen=HISTORY_MAX_ENTRIES)


def get_history() -> list[dict]:
    """현재까지 적재된 history 를 JSON 친화 list 로 반환."""
    return [
        {"t": ts, "uptimeSec": up, "daemonCount": dc}
        for ts, up, dc in _history
    ]


def _take_sample() -> None:
    """현재 시점 1 sample 적재."""
    try:
        status = cleanup_mod.get_system_status()
        _history.append((
            int(time.time() * 1000),
            status.get("uptimeSeconds"),
            int(status.get("staleDaemonCount") or 0),
        ))
    except Exception:  # noqa: BLE001 — sampler 가 background 영구 luminous
        log.exception("status_history: sample 실패")


async def sampler_loop() -> None:
    """helper 시작 시 background task — 60s 마다 status sample 적재."""
    log.info("status_history: starting sampler (interval=%.0fs, max=%d)",
             SAMPLE_INTERVAL_SEC, HISTORY_MAX_ENTRIES)
    # 첫 sample 즉시 (UI 가 helper 기동 직후 빈 차트 보지 않게)
    _take_sample()
    while True:
        try:
            await asyncio.sleep(SAMPLE_INTERVAL_SEC)
        except asyncio.CancelledError:
            log.info("status_history: sampler cancelled — exit")
            raise
        _take_sample()
