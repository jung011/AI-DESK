"""B Phase 2 — helper python broker.

backend 와 *단일 영속 ws* (`/ws/messages-broker?agentIds=...`) + helper loopback
ws endpoint (`/ws/messages-broker?agentId=...`) 가 mcp(bun) 들의 connection 받음.
backend 가 envelope push 시 toAgentId 보고 해당 loopback session 으로 fan-out.

Phase 2 MVP — inbound (backend → mcp) 라우팅 만. outbound (mcp → backend api/messages)
는 기존 helper proxy 그대로. Phase 3 에 outbound 도 broker ws 통일 가능.

Subscribe list 동기화:
    reporter 의 매 cycle 에서 backend `/api/desktop/local-info` response 의
    `matchedAgentIds` 를 broker.update_subscribed_ids 로 갱신. 변경 시 backend ws
    재연결 trigger.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web

if TYPE_CHECKING:
    from aiohttp.client import ClientWebSocketResponse

log = logging.getLogger(__name__)


class Broker:
    def __init__(self, backend_url: str) -> None:
        self.backend_url = backend_url.rstrip("/")
        # agent_id → loopback ws sessions (한 agent_id 의 여러 ws 가능)
        self._loopback: dict[str, set[web.WebSocketResponse]] = {}
        # 현재 subscribe 중인 agent_ids (backend ws 의 query 에 명시한 것)
        self._subscribed_ids: list[str] = []
        # backend 와의 단일 ws (강한 참조 — 재연결 trigger 용)
        self._backend_ws: ClientWebSocketResponse | None = None
        self._lock = asyncio.Lock()
        # 지수 backoff
        self._reconnect_delay = 1.0
        self._reconnect_min = 1.0
        self._reconnect_max = 30.0
        # background task strong ref ([[feedback-resource-cleanup-rule]])
        self._loop_task: asyncio.Task | None = None
        self._closing = False

    # ---- subscribe list 동기화 (reporter 가 매 cycle 호출) ----

    def update_subscribed_ids(self, agent_ids: list[str]) -> None:
        clean = sorted(a for a in agent_ids if a)
        if clean == self._subscribed_ids:
            return
        old_count = len(self._subscribed_ids)
        self._subscribed_ids = clean
        log.info("broker: subscribed_ids changed %d → %d", old_count, len(clean))
        # 현재 backend ws 가 떠있다면 close → 다음 cycle 에 새 agentIds 로 재연결
        ws = self._backend_ws
        if ws is not None and not ws.closed:
            # close 자체는 *async* — fire-and-forget 으로 띄우되 strong ref 보관.
            task = asyncio.create_task(ws.close(), name="broker-ws-reconnect-trigger")
            self._loopback.setdefault("__close_tasks__", set())  # 임시 — race 회피용 dummy
            self._loopback.pop("__close_tasks__", None)
            # task 의 reference 안 잡아도 close() 는 짧고 cancel 안 됨 — OK.
            del task

    # ---- loopback session registry ----

    async def register_loopback(self, agent_id: str, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._loopback.setdefault(agent_id, set()).add(ws)
        log.info(
            "broker: loopback register agent_id=%s total=%d",
            agent_id, len(self._loopback.get(agent_id, set())),
        )

    async def unregister_loopback(self, agent_id: str, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            bucket = self._loopback.get(agent_id)
            if bucket:
                bucket.discard(ws)
                if not bucket:
                    self._loopback.pop(agent_id, None)
        log.info("broker: loopback unregister agent_id=%s", agent_id)

    async def fan_out(self, envelope: dict) -> None:
        """backend envelope → 해당 toAgentId 의 loopback session 들."""
        to_agent_id = envelope.get("toAgentId")
        if not to_agent_id:
            return
        bucket = self._loopback.get(to_agent_id, set())
        if not bucket:
            log.debug("broker: fan_out skip — no loopback agent_id=%s", to_agent_id)
            return
        msg = json.dumps(envelope, ensure_ascii=False)
        sent = 0
        for ws in list(bucket):
            try:
                await ws.send_str(msg)
                sent += 1
            except (ConnectionError, RuntimeError) as e:
                log.warning(
                    "broker: fan_out send failed agent_id=%s err=%s",
                    to_agent_id, e,
                )
        log.info("broker: fan_out agent_id=%s sent=%d/%d", to_agent_id, sent, len(bucket))

    # ---- backend ws 영속 loop ----

    def start(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._closing = False
        self._loop_task = asyncio.create_task(self._run_loop(), name="broker-backend-loop")

    async def stop(self) -> None:
        self._closing = True
        ws = self._backend_ws
        if ws is not None and not ws.closed:
            try:
                await ws.close()
            except (ConnectionError, RuntimeError):
                pass
        task = self._loop_task
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._loop_task = None

    async def _run_loop(self) -> None:
        """background task — backend 와의 단일 ws 영속 유지 (지수 backoff)."""
        while not self._closing:
            if not self._subscribed_ids:
                # reporter 아직 안 돔 — wait 후 retry. lastIds=[] 로 connect 하면 reject (인증 실패)
                await asyncio.sleep(2)
                continue
            try:
                await self._run_once()
                # 정상 close (subscribe 변경 trigger 등) — backoff reset
                self._reconnect_delay = self._reconnect_min
            except (aiohttp.ClientError, OSError) as e:
                log.warning(
                    "broker: backend ws fail (%s) — reconnect in %.1fs",
                    e, self._reconnect_delay,
                )
            except Exception:  # noqa: BLE001
                log.exception("broker: backend loop iter unexpected")
            if self._closing:
                break
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._reconnect_max)

    async def _run_once(self) -> None:
        agent_ids_query = ",".join(self._subscribed_ids)
        wsbase = self.backend_url.replace("http://", "ws://").replace("https://", "wss://")
        url = f"{wsbase}/ws/messages-broker?agentIds={agent_ids_query}"
        log.info("broker: connecting backend ws subscribe_count=%d", len(self._subscribed_ids))
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                url,
                heartbeat=30.0,  # aiohttp 자동 ping/pong (C 와 같은 패턴 무료)
                autoping=True,
                timeout=aiohttp.ClientWSTimeout(ws_close=5.0),
            ) as ws:
                self._backend_ws = ws
                self._reconnect_delay = self._reconnect_min  # connect 성공 시 즉시 reset
                log.info("broker: backend ws connected")
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                envelope = json.loads(msg.data)
                            except json.JSONDecodeError:
                                continue
                            await self.fan_out(envelope)
                        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                            break
                finally:
                    self._backend_ws = None
                    log.info("broker: backend ws disconnected")


# ---------------------------------------------------------------------
# helper loopback ws endpoint — mcp(bun) 가 backend 대신 helper 로 ws connect.
# ---------------------------------------------------------------------

async def broker_ws_handler(request: web.Request) -> web.WebSocketResponse:
    """/ws/messages-broker?agentId=<id> — 각 mcp 의 1개 ws.

    Phase 2 MVP — outbound 메시지 (mcp → backend api/messages) 는 *기존 helper
    proxy* 그대로 사용. 여기는 *backend → mcp* 의 envelope fan-out 만.
    """
    agent_id = request.query.get("agentId", "").strip()
    if not agent_id:
        return web.Response(status=400, text="agentId required")

    broker: Broker | None = request.app.get("broker")
    if broker is None:
        return web.Response(status=503, text="broker not ready")

    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)
    await broker.register_loopback(agent_id, ws)
    log.info("broker_ws_handler: connected agent_id=%s", agent_id)
    try:
        async for msg in ws:
            # mcp 의 outbound message 는 Phase 3 까지 helper proxy 사용 — 여기서 ignore.
            if msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                break
    except (ConnectionError, RuntimeError) as e:
        log.warning("broker_ws_handler: recv err agent_id=%s: %s", agent_id, e)
    finally:
        await broker.unregister_loopback(agent_id, ws)
        log.info("broker_ws_handler: disconnected agent_id=%s", agent_id)
    return ws
