"""messages router — /api/messages/*. 9 endpoint.

path 매칭 순서 주의: literal path (/unread-count, /broadcast, /conversations, /audit, /events)
는 변수 path (/{message_id}) 보다 *위*에 등록해야 매칭 우선됨.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.deps import current_user, optional_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, fail, ok
from app.core.database import get_db
from app.messages.caller import resolve_caller_account_sn
from app.messages.schemas import (
    ConversationItem,
    MessageBroadcastRq,
    MessageBroadcastRs,
    MessageCreateRq,
    MessageItem,
    MessageListRs,
    UnreadCountRs,
)
from app.messages.service import MessageService
from app.messages.sse import broker

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "messages", "status": "ok"}


# ---- collection endpoints (literal path first) ----

@router.post("", response_model=ApiEnvelope[MessageItem])
async def create(body: MessageCreateRq, db: Session = Depends(get_db)) -> ApiEnvelope[MessageItem]:
    svc = MessageService(db)
    item = svc.create(body)
    return ok(item)


@router.get("", response_model=ApiEnvelope[MessageListRs])
async def list_messages(
    agentId: str = Query(...),  # noqa: N803
    direction: str = Query(default="all"),
    withId: str | None = Query(default=None),  # noqa: N803
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[MessageListRs]:
    """messages list — *caller 의 own agent 만* 조회 가능.

    caller 식별: cookie 의 user.account_sn 또는 agentId 자체의 owner_account_sn.
    agentId 의 owner != caller 면 403/empty. sameUser 격리.
    """
    caller_sn = resolve_caller_account_sn(db, user, agentId)
    if caller_sn is None:
        return fail(401, "unauthorized — provide cookie or valid agentId")  # type: ignore[return-value]
    svc = MessageService(db)
    return ok(svc.get_list(agentId, direction, withId, status, limit, caller_account_sn=caller_sn))


@router.get("/unread-count", response_model=ApiEnvelope[UnreadCountRs])
async def unread_count(
    agentId: str | None = Query(default=None),  # noqa: N803
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[UnreadCountRs]:
    """unread count — caller 의 own agent 만. agentId 박으면 그 agent 의 unread.
    cookie user 만 박으면 user 의 모든 agent unread.
    """
    caller_sn = resolve_caller_account_sn(db, user, agentId)
    if caller_sn is None:
        return fail(401, "unauthorized")  # type: ignore[return-value]
    svc = MessageService(db)
    return ok(svc.get_unread_count(agentId, caller_account_sn=caller_sn))


@router.post("/broadcast", response_model=ApiEnvelope[MessageBroadcastRs])
async def broadcast(
    body: MessageBroadcastRq, db: Session = Depends(get_db)
) -> ApiEnvelope[MessageBroadcastRs]:
    svc = MessageService(db)
    return ok(svc.broadcast(body))


@router.get("/conversations", response_model=ApiEnvelope[list[ConversationItem]])
async def conversations(
    agentId: str = Query(...),  # noqa: N803
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[list[ConversationItem]]:
    """conversation list — caller 의 own agent 만."""
    caller_sn = resolve_caller_account_sn(db, user, agentId)
    if caller_sn is None:
        return fail(401, "unauthorized")  # type: ignore[return-value]
    svc = MessageService(db)
    return ok(svc.get_conversations(agentId, caller_account_sn=caller_sn))


@router.get("/audit", response_model=ApiEnvelope[MessageListRs])
async def audit(
    status: str | None = Query(default=None),
    fromAgentId: str | None = Query(default=None),  # noqa: N803
    toAgentId: str | None = Query(default=None),  # noqa: N803
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[MessageListRs]:
    """audit — caller 의 own agent 가 from 또는 to 인 메시지만.

    옛 = 인증 없음 + filter 없음 → 전체 user 메시지 검색 노출 사고.
    fix = current_user 필수 + caller_account_sn 으로 own agent 만.
    """
    svc = MessageService(db)
    return ok(svc.audit(status, fromAgentId, toAgentId, q, limit, caller_account_sn=user.account_sn))


@router.get("/events")
async def events(catchupSince: float | None = None) -> StreamingResponse:  # noqa: N803
    """SSE stream — frontend / helper 가 subscribe. broadcast PoC.

    `event: message.created` / `event: connected` / `: keepalive` (15초).
    `catchupSince` (epoch sec) 박으면 broker 의 7s buffer 의 replay 박음.
    """
    return StreamingResponse(
        broker.event_stream(catchup_since_sec=catchupSince),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- item endpoints (variable path — must come AFTER literal path matches) ----

@router.get("/{message_id}", response_model=ApiEnvelope[MessageItem])
async def detail(
    message_id: str,
    callerAgentId: str | None = Query(default=None),  # noqa: N803
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[MessageItem]:
    """message detail — caller 가 from 또는 to 의 owner 인 메시지만.
    UUID 추측해서 다른 user 메시지 노출 차단.
    """
    caller_sn = resolve_caller_account_sn(db, user, callerAgentId)
    if caller_sn is None:
        return fail(401, "unauthorized")  # type: ignore[return-value]
    svc = MessageService(db)
    item = svc.detail(message_id, caller_account_sn=caller_sn)
    if item is None:
        return fail(404, "message not found")  # type: ignore[return-value]
    return ok(item)


@router.patch("/{message_id}/read", response_model=ApiEnvelope[None])
async def mark_read(
    message_id: str,
    agentId: str = Query(...),  # noqa: N803
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    svc = MessageService(db)
    ok_ = svc.mark_read(message_id, agentId)
    if not ok_:
        return fail(404, "message not found / already read / not for this agent")  # type: ignore[return-value]
    return ok(None)


@router.post("/{message_id}/ack", response_model=ApiEnvelope[None])
async def ack(message_id: str, db: Session = Depends(get_db)) -> ApiEnvelope[None]:
    svc = MessageService(db)
    svc.ack_delivered(message_id)
    return ok(None)
