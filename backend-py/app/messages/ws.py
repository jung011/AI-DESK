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
    """account_sn 별 활성 WebSocket sessions. 한 사용자의 multi tab/device 동시 접속 지원."""

    def __init__(self) -> None:
        self._sessions: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, account_sn: int, ws: WebSocket) -> None:
        async with self._lock:
            self._sessions.setdefault(account_sn, set()).add(ws)
        log.info("[ws-broker] register account_sn=%s total=%d", account_sn, self._total())

    async def unregister(self, account_sn: int, ws: WebSocket) -> None:
        async with self._lock:
            bucket = self._sessions.get(account_sn)
            if bucket:
                bucket.discard(ws)
                if not bucket:
                    self._sessions.pop(account_sn, None)
        log.info("[ws-broker] unregister account_sn=%s total=%d", account_sn, self._total())

    async def publish_to_account(self, account_sn: int, payload: dict[str, Any]) -> None:
        bucket = self._sessions.get(account_sn)
        if not bucket:
            return
        msg = json.dumps(payload, default=str, ensure_ascii=False)
        for ws in list(bucket):
            try:
                await ws.send_text(msg)
            except Exception as e:  # noqa: BLE001
                log.warning("[ws-broker] send failed account_sn=%s err=%s", account_sn, e)

    def _total(self) -> int:
        return sum(len(s) for s in self._sessions.values())


# 모듈 singleton — 같은 인스턴스를 service.create 와 ws endpoint 가 공유
ws_broker = WsBroker()


def _hash_bearer(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _looks_like_bearer(raw: str | None) -> bool:
    return bool(raw) and raw.startswith("aidesk_ext_")


def _authenticate(db: Session, cookie_token: str | None, agent_id: str | None, bearer_token: str | None) -> tuple[int, str | None] | None:
    """3경로 인증 — Spring JwtHandshakeInterceptor 1:1.

    Returns (account_sn, agent_id) 또는 None (인증 실패).
    """
    # 1) cookie JWT
    if cookie_token:
        user = AuthService.decode_access_token(cookie_token)
        if user is not None:
            return (user.account_sn, None)

    # 2) ?agentId=<UUID> — 내부 봇 어댑터
    if agent_id:
        repo = AgentRepository(db)
        agent: AiAgent | None = repo.find_by_agent_id_any_owner(agent_id)
        if agent is not None and agent.owner_account_sn is not None:
            return (agent.owner_account_sn, agent_id)
        log.warning("[ws-handshake] reject — agentId=%s not found", agent_id)
        return None

    # 3) ?token=aidesk_ext_... — 외부 AI Bearer token
    if _looks_like_bearer(bearer_token):
        repo = AgentRepository(db)
        token_hash = _hash_bearer(bearer_token)  # type: ignore[arg-type]
        # bearer_token_hash 컬럼으로 agent 조회 — Spring AgentMapper.selectByBearerTokenHash 와 동등
        match: AiAgent | None = None
        for a in repo.list_all_active():
            if a.bearer_token_hash == token_hash:
                match = a
                break
        if match is not None and match.owner_account_sn is not None:
            return (match.owner_account_sn, match.agent_id)
        log.warning("[ws-handshake] reject — bearer token not matched")
        return None

    log.warning("[ws-handshake] reject — no cookie / agentId / token")
    return None


def _toggle_status(db: Session, agent_id: str, new_status: str) -> None:
    """ws connect/disconnect 시점에 agent.status 토글. Spring AgentMapper.updateStatusSystem 동등."""
    repo = AgentRepository(db)
    repo.update_status_from_watcher(agent_id, new_status)
    db.commit()


async def messages_ws_endpoint(
    websocket: WebSocket,
    agentId: str | None = Query(default=None),  # noqa: N803
    token: str | None = Query(default=None),
) -> None:
    """WebSocket /ws/messages handler.

    cookie 는 websocket.cookies 에서 추출 — Spring JwtHandshakeInterceptor 의 SecurityContext 와 동일 효과.
    """
    cookie_token = websocket.cookies.get(settings.cookie_access_name)

    db = SessionLocal()
    try:
        auth = _authenticate(db, cookie_token, agentId, token)
        if auth is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        account_sn, ws_agent_id = auth

        await websocket.accept()
        await ws_broker.register(account_sn, websocket)

        # connect → agent status='idle' (Spring 동등)
        if ws_agent_id:
            _toggle_status(db, ws_agent_id, "idle")
            log.info("[ws-handler] connect → status=idle agentId=%s", ws_agent_id)

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
            await ws_broker.unregister(account_sn, websocket)
            # disconnect → agent status='offline'
            if ws_agent_id:
                try:
                    _toggle_status(db, ws_agent_id, "offline")
                    log.info("[ws-handler] disconnect → status=offline agentId=%s", ws_agent_id)
                except Exception:  # noqa: BLE001
                    log.exception("[ws-handler] disconnect status toggle failed")
    finally:
        db.close()
