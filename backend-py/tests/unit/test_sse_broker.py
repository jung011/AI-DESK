"""SseBroker 단위 test — recipient 별 emitter 분리 (rc25) 검증."""
import asyncio
import json

import pytest

from app.messages.sse import SseBroker


async def _drain_until_match(q: asyncio.Queue[str], event_type: str, timeout: float = 0.5) -> dict | None:
    """queue 에서 connected/keepalive 같은 non-match 는 흘리고 event_type 만 잡아 반환."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            msg = await asyncio.wait_for(q.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        if msg.startswith(f"event: {event_type}\n"):
            return json.loads(msg.split("data: ", 1)[1].split("\n\n", 1)[0])


@pytest.mark.asyncio
async def test_filter_match_receives() -> None:
    """tmux_filter 안 target = subscribe 한 queue 가 받음."""
    b = SseBroker()
    q = await b.subscribe(frozenset({"aidesk-foo"}))
    b.publish("message.deliver", {"toTmuxSession": "aidesk-foo", "msg": "hi"})
    payload = await _drain_until_match(q, "message.deliver")
    assert payload is not None
    assert payload["msg"] == "hi"


@pytest.mark.asyncio
async def test_filter_no_leakage_to_other_recipient() -> None:
    """다른 tmux 의 event 가 *애초에* queue 에 enqueue 안 됨 (cross-recipient leakage 차단)."""
    b = SseBroker()
    q_foo = await b.subscribe(frozenset({"aidesk-foo"}))
    q_bar = await b.subscribe(frozenset({"aidesk-bar"}))
    b.publish("message.deliver", {"toTmuxSession": "aidesk-foo", "msg": "to_foo"})

    foo_payload = await _drain_until_match(q_foo, "message.deliver", timeout=0.3)
    bar_payload = await _drain_until_match(q_bar, "message.deliver", timeout=0.3)
    assert foo_payload is not None and foo_payload["msg"] == "to_foo"
    assert bar_payload is None, "bar subscriber 가 foo event 받으면 안 됨"


@pytest.mark.asyncio
async def test_broadcast_subscriber_receives_all_targeted_events() -> None:
    """filter 빈 subscriber (dashboard 등) 는 모든 targeted event 받음 — backward compat."""
    b = SseBroker()
    q_all = await b.subscribe(None)  # broadcast
    b.publish("message.deliver", {"toTmuxSession": "aidesk-foo", "msg": "1"})
    b.publish("message.deliver", {"toTmuxSession": "aidesk-bar", "msg": "2"})

    first = await _drain_until_match(q_all, "message.deliver", timeout=0.3)
    second = await _drain_until_match(q_all, "message.deliver", timeout=0.3)
    msgs = {p["msg"] for p in (first, second) if p is not None}
    assert msgs == {"1", "2"}


@pytest.mark.asyncio
async def test_event_without_tmux_only_to_broadcast() -> None:
    """toTmuxSession 없는 event (agent 상태 등) 는 broadcast subscriber 만 받음.

    rc25 design — filter 박은 subscriber 가 자기 recipient 외 event 받으면 dashboard
    의 *내 tmux 메시지* 와 *다른 agent 상태 broadcast* 가 섞임. broadcast subscriber
    가 그 역할 — 자기는 그 dashboard 처럼 모든 event 받기 자처.
    """
    b = SseBroker()
    q_specific = await b.subscribe(frozenset({"aidesk-foo"}))
    q_all = await b.subscribe(None)
    b.publish("agent.status", {"agentId": "abc", "status": "idle"})  # toTmuxSession 없음

    specific = await _drain_until_match(q_specific, "agent.status", timeout=0.3)
    broadcast = await _drain_until_match(q_all, "agent.status", timeout=0.3)
    assert specific is None, "filter 박은 subscriber 는 recipient-less event 받으면 안 됨"
    assert broadcast is not None


@pytest.mark.asyncio
async def test_unsubscribe_cleans_up_by_tmux() -> None:
    """unsubscribe 시 by_tmux 의 empty set 정리."""
    b = SseBroker()
    q = await b.subscribe(frozenset({"aidesk-foo", "aidesk-bar"}))
    assert "aidesk-foo" in b._by_tmux
    assert "aidesk-bar" in b._by_tmux
    b.unsubscribe(q)
    assert b._by_tmux == {}, "empty set 인 tmux 키는 dict 에서 제거되어야 함"
    assert b.total_subscribers == 0


@pytest.mark.asyncio
async def test_multi_filter_subscriber_receives_each_target() -> None:
    """한 subscriber 가 여러 tmux filter — 각 target event 모두 받지만 중복 X."""
    b = SseBroker()
    q = await b.subscribe(frozenset({"aidesk-foo", "aidesk-bar"}))
    b.publish("message.deliver", {"toTmuxSession": "aidesk-foo", "msg": "f"})
    b.publish("message.deliver", {"toTmuxSession": "aidesk-bar", "msg": "b"})
    b.publish("message.deliver", {"toTmuxSession": "aidesk-baz", "msg": "z"})  # 매칭 X

    received = []
    for _ in range(3):
        p = await _drain_until_match(q, "message.deliver", timeout=0.2)
        if p is None:
            break
        received.append(p["msg"])
    assert sorted(received) == ["b", "f"]


@pytest.mark.asyncio
async def test_queue_full_drops_event_not_raises() -> None:
    """slow client (queue full) 면 drop. broker 가 raise 하지 않아 다른 subscriber 영향 X."""
    b = SseBroker()
    q_slow = await b.subscribe(frozenset({"aidesk-foo"}))
    # queue 채워서 full 상태로
    for _ in range(100):
        q_slow.put_nowait("filler")
    q_other = await b.subscribe(frozenset({"aidesk-foo"}))
    # raise 없이 publish 끝나야 함 + q_other 는 정상 받음
    b.publish("message.deliver", {"toTmuxSession": "aidesk-foo", "msg": "still_ok"})
    payload = await _drain_until_match(q_other, "message.deliver", timeout=0.3)
    assert payload is not None and payload["msg"] == "still_ok"
