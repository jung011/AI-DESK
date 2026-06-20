"""SSE broker — recipient 별 emitter 분리 (rc20).

옛 broadcast PoC ([[sse-emitter-separation-followup]]) 한계 fix:
- 옛: 모든 subscriber 에 fan-out → 99% client 가 event 받자마자 skip
- 새: subscribe 시 *tmux session filter* + publish 시 매칭 만 push

스레드/asyncio 안전 — asyncio.Queue 사용. backward compatible — filter 비어있으면 옛 broadcast 동작.
"""
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)


class SseBroker:
    """프로세스 안 in-memory broker. K8s replica > 1 시 Redis pub/sub 같은 외부 broker 필요.

    subscriber 별 tmux_filter — publish 시 event.payload.toTmuxSession 매칭 시만 push.
    filter 빈 값 = 모든 event 받음 (옛 broadcast 호환 — dashboard frontend 등).
    """

    def __init__(self) -> None:
        # queue → tmux_filter (frozenset). filter 빈 = 모든 event 수신.
        self._subscribers: dict[asyncio.Queue[str], frozenset[str]] = {}

    async def subscribe(self, tmux_filter: frozenset[str] | None = None) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers[q] = tmux_filter or frozenset()
        log.info(
            "[sse-broker] subscribe — filter=%s total_subscribers=%d",
            list(tmux_filter) if tmux_filter else "ALL", len(self._subscribers),
        )
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subscribers.pop(q, None)
        log.info("[sse-broker] unsubscribe — total_subscribers=%d", len(self._subscribers))

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """매칭 subscriber 에만 push. queue full = drop (slow client 대비).

        매칭 규칙:
        - subscriber 의 tmux_filter 가 비어있으면 = 모든 event 수신 (옛 broadcast)
        - filter 있으면 = event.toTmuxSession 가 그 filter set 안 일 때만 push
        - event 에 toTmuxSession 없으면 = filter 무관 모든 subscriber 받음 (예: agent 상태 broadcast)
        """
        payload = json.dumps(data, default=str, ensure_ascii=False)
        msg = f"event: {event_type}\ndata: {payload}\n\n"
        target_tmux = (data.get("toTmuxSession") or "").strip()
        sent = 0
        skipped_filter = 0
        for q, tmux_filter in list(self._subscribers.items()):
            # filter 빈 = 모든 event. filter 있으면 target 매칭 확인.
            if tmux_filter and target_tmux and target_tmux not in tmux_filter:
                skipped_filter += 1
                continue
            try:
                q.put_nowait(msg)
                sent += 1
            except asyncio.QueueFull:
                log.warning("sse subscriber queue full — dropping event")
        if target_tmux:
            log.info(
                "[sse-broker] publish event=%s target=%s sent=%d skip_filter=%d",
                event_type, target_tmux, sent, skipped_filter,
            )

    async def event_stream(self, tmux_filter: frozenset[str] | None = None) -> AsyncIterator[str]:
        """starlette EventSourceResponse 패턴. tmux_filter = subscribe filter (rc20)."""
        q = await self.subscribe(tmux_filter)
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self.unsubscribe(q)


# 모듈 단위 singleton — app.main 의 lifespan 안에서 같은 인스턴스 공유
broker = SseBroker()
