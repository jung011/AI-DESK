"""messages router — /api/messages/*. 9 endpoint.

path 매칭 순서 주의: literal path (/unread-count, /broadcast, /conversations, /audit, /events)
는 변수 path (/{message_id}) 보다 *위*에 등록해야 매칭 우선됨.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.response import ApiEnvelope, fail, ok
from app.core.database import get_db
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
    db: Session = Depends(get_db),
) -> ApiEnvelope[MessageListRs]:
    svc = MessageService(db)
    return ok(svc.get_list(agentId, direction, withId, status, limit))


@router.get("/unread-count", response_model=ApiEnvelope[UnreadCountRs])
async def unread_count(
    agentId: str | None = Query(default=None),  # noqa: N803
    db: Session = Depends(get_db),
) -> ApiEnvelope[UnreadCountRs]:
    svc = MessageService(db)
    return ok(svc.get_unread_count(agentId))


@router.post("/broadcast", response_model=ApiEnvelope[MessageBroadcastRs])
async def broadcast(
    body: MessageBroadcastRq, db: Session = Depends(get_db)
) -> ApiEnvelope[MessageBroadcastRs]:
    svc = MessageService(db)
    return ok(svc.broadcast(body))


@router.get("/conversations", response_model=ApiEnvelope[list[ConversationItem]])
async def conversations(
    agentId: str = Query(...),  # noqa: N803
    db: Session = Depends(get_db),
) -> ApiEnvelope[list[ConversationItem]]:
    svc = MessageService(db)
    return ok(svc.get_conversations(agentId))


@router.get("/audit", response_model=ApiEnvelope[MessageListRs])
async def audit(
    status: str | None = Query(default=None),
    fromAgentId: str | None = Query(default=None),  # noqa: N803
    toAgentId: str | None = Query(default=None),  # noqa: N803
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> ApiEnvelope[MessageListRs]:
    svc = MessageService(db)
    return ok(svc.audit(status, fromAgentId, toAgentId, q, limit))


@router.get("/events")
async def events() -> StreamingResponse:
    """SSE stream — frontend / helper 가 subscribe. broadcast PoC.

    `event: message.created` / `event: connected` / `: keepalive` (15초).
    """
    return StreamingResponse(
        broker.event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- item endpoints (variable path — must come AFTER literal path matches) ----

@router.get("/{message_id}", response_model=ApiEnvelope[MessageItem])
async def detail(message_id: str, db: Session = Depends(get_db)) -> ApiEnvelope[MessageItem]:
    svc = MessageService(db)
    item = svc.detail(message_id)
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
