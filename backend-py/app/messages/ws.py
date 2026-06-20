"""WebSocket broker + endpoint — Spring 의 MessageWebSocketBroker + Handler + JwtHandshakeInterceptor 1:1.

Endpoint: /ws/messages
인증 3경로:
1. cookie JWT (browser dashboard)
2. ?agentId=<UUID> (내부 봇 어댑터 — cookie 없음, 사내 망)
3. ?token=aidesk_ext_... (외부 AI Bearer token — Phase 2)

publish_to_account: account_sn 의 모든 활성 session 에 push. broadcast 한계 회피.
"""
import asyncio
import hashlib
import json
import logging
from typing import Any

from fastapi import Query, WebSocket, WebSocketDisconnect, WebSocketException, status
from sqlalchemy.orm import Session

from app.agents.models import AiAgent
from app.agents.repository import AgentRepository
from app.auth.service import AuthService
from app.core.config import get_settings
from app.core.database import SessionLocal

log = logging.getLogger(__name__)
settings = get_settings()


class WsBroker:
    """account_sn 별 활성 WebSocket sessions + agent_id 별 추적 (rc12 — ws-aware delivered).

    multi tab/device 동시 접속 + service.create 가 *receiver 의 ws session 살아있는지*
    판정 가능 → markDelivered 자동화.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, set[WebSocket]] = {}
        self._by_agent: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, account_sn: int, agent_id: str | None, ws: WebSocket) -> None:
        async with self._lock:
            self._sessions.setdefault(account_sn, set()).add(ws)
            if agent_id:
                self._by_agent.setdefault(agent_id, set()).add(ws)
        log.info(
            "[ws-broker] register account_sn=%s agent_id=%s total=%d agent_sessions=%d",
            account_sn, agent_id, self._total(),
            len(self._by_agent.get(agent_id, set())) if agent_id else 0,
        )

    async def unregister(self, account_sn: int, agent_id: str | None, ws: WebSocket) -> None:
        async with self._lock:
            bucket = self._sessions.get(account_sn)
            if bucket:
                bucket.discard(ws)
                if not bucket:
                    self._sessions.pop(account_sn, None)
            if agent_id:
                a_bucket = self._by_agent.get(agent_id)
                if a_bucket:
                    a_bucket.discard(ws)
                    if not a_bucket:
                        self._by_agent.pop(agent_id, None)
        log.info(
            "[ws-broker] unregister account_sn=%s agent_id=%s total=%d",
            account_sn, agent_id, self._total(),
        )

    async def publish_to_account(self, account_sn: int, payload: dict[str, Any]) -> None:
        bucket = self._sessions.get(account_sn)
        if not bucket:
            log.info("[ws-broker] publish skipped — no sessions account_sn=%s", account_sn)
            return
        msg = json.dumps(payload, default=str, ensure_ascii=False)
        sent = 0
        for ws in list(bucket):
            try:
                await ws.send_text(msg)
                sent += 1
            except Exception as e:  # noqa: BLE001
                log.warning("[ws-broker] send failed account_sn=%s err=%s", account_sn, e)
        log.info("[ws-broker] published account_sn=%s sent=%d/%d", account_sn, sent, len(bucket))

    def count_sessions_for_agent(self, agent_id: str) -> int:
        """Spring countSessionsForAgent 동등. service.create 의 ws-aware delivered 판정."""
        if not agent_id:
            return 0
        return len(self._by_agent.get(agent_id, set()))

    def _total(self) -> int:
        return sum(len(s) for s in self._sessions.values())


# 모듈 singleton — 같은 인스턴스를 service.create 와 ws endpoint 가 공유
ws_broker = WsBroker()


def _hash_bearer(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _looks_like_bearer(raw: str | None) -> bool:
    # Spring BearerTokenUtil 정합 — rc17 부터 새 token = 'aidesk_ext_' prefix.
    # 옛 prefix 없는 token (rc16 이전 발급) 은 rotate 필요.
    return bool(raw) and raw.startswith("aidesk_ext_")


def _authenticate(db: Session, cookie_token: str | None, agent_id: str | None, bearer_token: str | None) -> tuple[int, str | None] | None:
    """3경로 인증 — Spring JwtHandshakeInterceptor 1:1.

    Returns (account_sn, agent_id) 또는 None (인증 실패).

    **우선순위 (rc33 변경)** — 명시적 인증 (bearer / agentId) 가 cookie 보다 우선.
    이유: dashboard 와 같은 origin (kaflix.internal) 에서 외부 AI mcp 의 ws connect
    시 *browser 의 cookie 자동 첨부* 가 backend 의 cookie path 통과 → agent_id=null
    반환 → _toggle_status 의 idle 마킹 path 안 거침. bearer 가 *명시적 인증 의도*
    이므로 cookie 보다 먼저 검사.
    """
    log.info(
        "[ws-handshake] start — cookie=%s agentId=%s bearer=%s",
        bool(cookie_token), bool(agent_id), bool(bearer_token),
    )
    # 1) ?token=aidesk_ext_... — 외부 AI Bearer token (명시적 외부 인증 — 가장 먼저 처리)
    if _looks_like_bearer(bearer_token):
        repo = AgentRepository(db)
        token_hash = _hash_bearer(bearer_token)  # type: ignore[arg-type]
        match: AiAgent | None = None
        for a in repo.list_all_active():
            if a.bearer_token_hash == token_hash:
                match = a
                break
        if match is not None and match.owner_account_sn is not None:
            log.info(
                "[ws-handshake] OK via bearer agentId=%s owner=%s name=%s",
                match.agent_id, match.owner_account_sn, match.agent_name,
            )
            return (match.owner_account_sn, match.agent_id)
        log.warning("[ws-handshake] reject — bearer token not matched (token_hash=%s...)", token_hash[:12])
        return None

    # 2) ?agentId=<UUID> — 내부 봇 어댑터 (명시적 agent 인증)
    if agent_id:
        repo = AgentRepository(db)
        agent: AiAgent | None = repo.find_by_agent_id_any_owner(agent_id)
        if agent is not None and agent.owner_account_sn is not None:
            log.info("[ws-handshake] OK via agentId=%s owner=%s", agent_id, agent.owner_account_sn)
            return (agent.owner_account_sn, agent_id)
        log.warning("[ws-handshake] reject — agentId=%s not found", agent_id)
        return None

    # 3) cookie JWT (frontend dashboard default — agent_id 없음)
    if cookie_token:
        user = AuthService.decode_access_token(cookie_token)
        if user is not None:
            log.info("[ws-handshake] OK via cookie account_sn=%s", user.account_sn)
            return (user.account_sn, None)
        log.warning("[ws-handshake] cookie present but decode failed")

    log.warning("[ws-handshake] reject — no cookie / agentId / token")
    return None


def _toggle_status(db: Session, agent_id: str, new_status: str) -> None:
    """ws connect/disconnect 시점에 agent.status 토글. Spring AgentMapper.updateStatusSystem 동등.

    *진단용 trace SSE event* — 외부에서 직접 backend 흐름 확인 가능. 안정화 후 제거.
    """
    repo = AgentRepository(db)
    try:
        n = repo.update_status_from_watcher(agent_id, new_status)
        db.commit()
        log.info("[ws-toggle-status] agentId=%s status=%s rowcount=%d", agent_id, new_status, n)
        # SSE trace — frontend 가 진행 확인 가능 (rc31)
        from app.messages.sse import broker as _broker
        _broker.publish("ws.toggle.trace", {
            "agentId": agent_id,
            "status": new_status,
            "rowcount": n,
        })
    except Exception as e:  # noqa: BLE001
        log.exception("[ws-toggle-status] failed agentId=%s status=%s", agent_id, new_status)
        from app.messages.sse import broker as _broker
        _broker.publish("ws.toggle.trace", {
            "agentId": agent_id,
            "status": new_status,
            "error": str(e),
        })
        raise


async def messages_ws_endpoint(
    websocket: WebSocket,
    agentId: str | None = Query(default=None),  # noqa: N803
    token: str | None = Query(default=None),
) -> None:
    """WebSocket /ws/messages handler.

    cookie 는 websocket.cookies 에서 추출 — Spring JwtHandshakeInterceptor 의 SecurityContext 와 동일 효과.
    """
    cookie_token = websocket.cookies.get(settings.cookie_access_name)
    _trace_id = f"ws-{id(websocket)}"
    ws_broker_module = None  # late import 차단용
    try:
        from app.messages.sse import broker as _br
        ws_broker_module = _br
        _br.publish("ws.trace", {"stage": "enter", "traceId": _trace_id, "hasCookie": bool(cookie_token), "hasAgentId": bool(agentId), "hasToken": bool(token)})
    except Exception:  # noqa: BLE001
        log.exception("[ws-trace] publish enter failed")

    db = SessionLocal()
    try:
        auth = _authenticate(db, cookie_token, agentId, token)
        if ws_broker_module:
            ws_broker_module.publish("ws.trace", {"stage": "authenticated", "traceId": _trace_id, "ok": auth is not None})
        if auth is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        account_sn, ws_agent_id = auth

        await websocket.accept()
        if ws_broker_module:
            ws_broker_module.publish("ws.trace", {"stage": "accepted", "traceId": _trace_id, "agentId": ws_agent_id})

        await ws_broker.register(account_sn, ws_agent_id, websocket)
        if ws_broker_module:
            ws_broker_module.publish("ws.trace", {"stage": "registered", "traceId": _trace_id, "agentId": ws_agent_id})

        # connect → agent status='idle' (Spring 동등)
        if ws_agent_id:
            _toggle_status(db, ws_agent_id, "idle")
            log.info("[ws-handler] connect → status=idle agentId=%s account_sn=%s", ws_agent_id, account_sn)
        else:
            log.info("[ws-handler] connect (cookie path, no agent_id binding) account_sn=%s", account_sn)

        try:
            # 클라이언트 → 서버 메시지는 PoC 단계 ignore (Spring 도 동일). receive loop 만 유지.
            while True:
                _ = await websocket.receive_text()
                # 무시
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning("[ws-handler] recv loop crashed: %s", e)
        finally:
            await ws_broker.unregister(account_sn, ws_agent_id, websocket)
            # rc19 design 정정 — ws disconnect ≠ claude exit. session close 만으로 offline
            # 마킹 금지. mcp ws 의 분 단위 disconnect/reconnect cycle 시 false offline
            # 방지. status='offline' 은 helper 의 명시적 종료 보고 (tmux 없음) 또는 agent
            # delete 만. ws session 만 status 결정하지 않음 — idle 유지.
            if ws_agent_id:
                try:
                    remaining = ws_broker.count_sessions_for_agent(ws_agent_id)
                    log.info(
                        "[ws-handler] disconnect agentId=%s remaining_sessions=%d (status unchanged)",
                        ws_agent_id, remaining,
                    )
                except Exception:  # noqa: BLE001
                    log.exception("[ws-handler] disconnect log failed")
    finally:
        db.close()
