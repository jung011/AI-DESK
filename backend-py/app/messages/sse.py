"""SSE broker — 메시지 도착 시 모든 client 에 push.

[[sse-emitter-separation-followup]] = recipient 별 emitter 분리 follow-up. 현재는 broadcast
PoC. 모든 client 가 모든 event 받음 + frontend 가 to_agent_id 매칭 후 필터.

스레드/asyncio 안전 — asyncio.Queue 사용. event_stream() 이 client 별 queue 등록 + iterate.
"""
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)


class SseBroker:
    """프로세스 안 in-memory broker. K8s replica > 1 시 Redis pub/sub 같은 외부 broker 필요."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    async def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subscribers.discard(q)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """모든 subscriber 에 push. queue full 이면 drop (slow client 대비)."""
        payload = json.dumps(data, default=str, ensure_ascii=False)
        msg = f"event: {event_type}\ndata: {payload}\n\n"
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning("sse subscriber queue full — dropping event")

    async def event_stream(self) -> AsyncIterator[str]:
        """starlette EventSourceResponse 같은 패턴. text/event-stream 의 chunk yield."""
        q = await self.subscribe()
        try:
            # 초기 connected 신호
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    # 15초 heartbeat — 프록시/load balancer 의 idle timeout 회피
                    yield ": keepalive\n\n"
        finally:
            self.unsubscribe(q)


# 모듈 단위 singleton — app.main 의 lifespan 안에서 같은 인스턴스 공유
broker = SseBroker()
