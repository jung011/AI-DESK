"""SSE broker — recipient 별 emitter 분리 (rc25).

이전 구조 (rc20) = 모든 subscriber 를 단일 list 에 두고 publish 시 for-loop fan-out
+ skip-by-filter. subscriber N 명일 때 publish 가 O(N).

새 구조 (rc25) = recipient (tmux_session) 별 set + filter 없는 broadcast set 분리.
publish 시 target tmux 의 set 만 직접 lookup → O(1) (matched subscribers 수에 비례
만 push). 다른 recipient 의 event 가 다른 subscriber queue 에 *애초에 enqueue 안 됨*
= cross-recipient leakage 차단.

스레드/asyncio 안전 — asyncio.Queue + dict/set 작업은 single event loop 안에서 진행.
backward compatible — filter 빈 subscriber 는 broadcast set 으로 가서 *모든 event*
수신 (dashboard frontend 등 옛 동작).
"""
import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)

# 7s short-lived buffer — helper sse_consumer 의 reconnect 동안 분실 event 복구.
# subscribe 시 ?catchupSince=<epoch_ms> 박으면 stream 시작 직전에 buffer 의
# *catchupSince 보다 새* + *tmux_filter 매칭* event 들을 replay.
# 7s 너머는 분실 — 사용자가 재전송. broker = 메모리 only, K8s replica > 1 시 외부 broker 필요.
_BUFFER_TTL_SEC = 7.0


class SseBroker:
    """프로세스 안 in-memory broker. K8s replica > 1 시 Redis pub/sub 같은 외부 broker 필요.

    구조:
    - `_by_tmux[tmux]` = set of queues — 그 tmux 를 filter 에 박은 subscriber.
    - `_broadcast` = set of queues — filter 비어있는 subscriber (모든 event 수신).

    publish target:
    - `data.toTmuxSession` 있음 → `_by_tmux[target]` ∪ `_broadcast`
    - `data.toTmuxSession` 없음 (예: agent 상태) → 모든 subscriber (broadcast + 모든 by_tmux 합집합)
    """

    def __init__(self) -> None:
        self._by_tmux: dict[str, set[asyncio.Queue[str]]] = {}
        self._broadcast: set[asyncio.Queue[str]] = set()
        # ring buffer — 직전 _BUFFER_TTL_SEC 안 publish event 들 보관.
        # entry = (epoch_sec, target_tmux_or_empty, raw_sse_msg). publish 마다 *오래된 entry
        # 머리에서 삭제* lazy cleanup. subscribe catchup 의 source.
        self._buffer: list[tuple[float, str, str]] = []

    @property
    def total_subscribers(self) -> int:
        """unique subscriber 수 — broadcast + 모든 by_tmux 합집합. 같은 queue 가 여러
        tmux 에 박혀있을 수 있어 단순 합산 X.
        """
        unique: set[asyncio.Queue[str]] = set(self._broadcast)
        for qs in self._by_tmux.values():
            unique |= qs
        return len(unique)

    async def subscribe(self, tmux_filter: frozenset[str] | None = None) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        if not tmux_filter:
            self._broadcast.add(q)
        else:
            for t in tmux_filter:
                self._by_tmux.setdefault(t, set()).add(q)
        log.info(
            "[sse-broker] subscribe — filter=%s total=%d (by_tmux=%d broadcast=%d)",
            sorted(tmux_filter) if tmux_filter else "ALL",
            self.total_subscribers, len(self._by_tmux), len(self._broadcast),
        )
        return q

    def replay_since(
        self,
        catchup_since_sec: float,
        tmux_filter: frozenset[str] | None,
    ) -> list[str]:
        """buffer 의 catchup_since 보다 새 + tmux_filter 매칭 event 들 반환.

        helper sse_consumer 의 reconnect 직후 호출 — *놓친 7s 안* event 자동 복구.
        - target_tmux 가 비어있으면 (recipient 무관 event) 모든 subscriber 한테 가는 거지만
          replay 에서는 *tmux_filter 박은 subscriber* 한테는 그게 *실시간 publish 와 정합*
          하도록 포함시킴. broadcast subscriber (filter None) 는 모든 entry 받음.
        """
        now = time.time()
        cutoff = max(catchup_since_sec, now - _BUFFER_TTL_SEC)
        out: list[str] = []
        for ts, target, msg in self._buffer:
            if ts <= cutoff:
                continue
            if tmux_filter is None:
                out.append(msg)
                continue
            # filter 있는 subscriber 는 *target 빈 event 만* 받음 (toTmuxSession 무관) 또는
            # *자기 filter 에 박힌 target* 만 받음. publish 의 logic 과 정합.
            if not target:
                # 옛 publish 의 ` toTmuxSession 무관 = broadcast 만` 정합 — filter subscriber
                # 는 *그 event* 안 받음. skip.
                continue
            if target in tmux_filter:
                out.append(msg)
        return out

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._broadcast.discard(q)
        empty: list[str] = []
        for t, qs in self._by_tmux.items():
            qs.discard(q)
            if not qs:
                empty.append(t)
        for t in empty:
            self._by_tmux.pop(t, None)
        log.info(
            "[sse-broker] unsubscribe — total=%d (by_tmux=%d broadcast=%d)",
            self.total_subscribers, len(self._by_tmux), len(self._broadcast),
        )

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """target lookup → 매칭 subscriber 의 queue 에만 enqueue. queue full = drop.

        target 결정:
        - data 안 'toTmuxSession' 가 있으면 → `_by_tmux[target]` (없으면 빈 set) ∪ `_broadcast`
        - 없으면 → broadcast 의 모든 subscriber (예: agent 상태처럼 recipient 무관 event)
        """
        payload = json.dumps(data, default=str, ensure_ascii=False)
        msg = f"event: {event_type}\ndata: {payload}\n\n"
        target_tmux = (data.get("toTmuxSession") or "").strip()

        targets: set[asyncio.Queue[str]]
        if target_tmux:
            targets = set(self._broadcast) | self._by_tmux.get(target_tmux, set())
        else:
            # toTmuxSession 무관 event — broadcast 만. by_tmux 의 specific subscriber 에는
            # *그 tmux 의 event 만* 가야 cross-recipient leakage 안 남. rc25 design 의 핵심.
            targets = set(self._broadcast)

        sent = 0
        for q in targets:
            try:
                q.put_nowait(msg)
                sent += 1
            except asyncio.QueueFull:
                log.warning("sse subscriber queue full — dropping event=%s", event_type)

        # 7s buffer 에 entry 박음 — reconnect 시 catchup_since 으로 replay 가능.
        # 매 publish 마다 *오래된 entry 머리에서 lazy cleanup* (TTL 7s).
        now = time.time()
        self._buffer.append((now, target_tmux, msg))
        cutoff = now - _BUFFER_TTL_SEC
        # head 부분만 (append-only 라 head 가 가장 오래된 entry)
        idx = 0
        for i, (ts, _, _) in enumerate(self._buffer):
            if ts > cutoff:
                idx = i
                break
        else:
            idx = len(self._buffer)
        if idx > 0:
            self._buffer = self._buffer[idx:]

        if target_tmux:
            log.info(
                "[sse-broker] publish event=%s target=%s sent=%d (matched=%d broadcast=%d buf=%d)",
                event_type, target_tmux, sent,
                len(self._by_tmux.get(target_tmux, set())), len(self._broadcast), len(self._buffer),
            )

    async def event_stream(
        self,
        tmux_filter: frozenset[str] | None = None,
        catchup_since_sec: float | None = None,
    ) -> AsyncIterator[str]:
        """starlette EventSourceResponse 패턴. tmux_filter = subscribe filter.

        catchup_since_sec 박으면 (helper sse_consumer 의 reconnect 시 마지막 성공 시각)
        connected event 직후 + 실시간 stream 시작 전에 *7s buffer 의 새 event* replay.
        """
        q = await self.subscribe(tmux_filter)
        try:
            yield "event: connected\ndata: {}\n\n"
            # catchup replay — reconnect 시 분실 7s 안 event 복구
            if catchup_since_sec is not None:
                replayed = self.replay_since(catchup_since_sec, tmux_filter)
                if replayed:
                    log.info(
                        "[sse-broker] catchup replay since=%.3f count=%d filter=%s",
                        catchup_since_sec, len(replayed),
                        sorted(tmux_filter) if tmux_filter else "ALL",
                    )
                for replay_msg in replayed:
                    yield replay_msg
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
