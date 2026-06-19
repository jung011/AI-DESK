"""messages router — /api/messages/*. 핵심 6 endpoint.

이번 turn 포함:
- POST   /api/messages
- GET    /api/messages/{messageId}
- GET    /api/messages
- GET    /api/messages/unread-count
- PATCH  /api/messages/{messageId}/read
- POST   /api/messages/{messageId}/ack

다음 turn 포함 예정:
- POST   /api/messages/broadcast
- GET    /api/messages/conversations
- GET    /api/messages/audit
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import ApiEnvelope, fail, ok
from app.core.database import get_db
from app.messages.schemas import MessageCreateRq, MessageItem, MessageListRs, UnreadCountRs
from app.messages.service import MessageService

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "messages", "status": "ok"}


@router.post("", response_model=ApiEnvelope[MessageItem])
async def create(body: MessageCreateRq, db: Session = Depends(get_db)) -> ApiEnvelope[MessageItem]:
    svc = MessageService(db)
    item = svc.create(body)
    return ok(item)


@router.get("/unread-count", response_model=ApiEnvelope[UnreadCountRs])
async def unread_count(
    agentId: str | None = Query(default=None),  # noqa: N803
    db: Session = Depends(get_db),
) -> ApiEnvelope[UnreadCountRs]:
    svc = MessageService(db)
    return ok(svc.get_unread_count(agentId))


@router.get("/{message_id}", response_model=ApiEnvelope[MessageItem])
async def detail(message_id: str, db: Session = Depends(get_db)) -> ApiEnvelope[MessageItem]:
    svc = MessageService(db)
    item = svc.detail(message_id)
    if item is None:
        return fail(404, "message not found")  # type: ignore[return-value]
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
