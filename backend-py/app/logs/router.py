"""logs router — /api/action-logs + /api/logs. Spring LogController 와 1:1.

router prefix = /api (main.py 에서 mount).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import ApiEnvelope, ok
from app.core.database import get_db
from app.logs.schemas import ActionLogCreateRq, LogFeedItem
from app.logs.service import LogService

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "logs", "status": "ok"}


@router.post("/action-logs", response_model=ApiEnvelope[str])
async def record_action(
    body: ActionLogCreateRq, db: Session = Depends(get_db)
) -> ApiEnvelope[str]:
    """claude PostToolUse hook 호출. 인증 없음 (PoC)."""
    svc = LogService(db)
    return ok(svc.record_action(body))


@router.get("/logs", response_model=ApiEnvelope[list[LogFeedItem]])
async def feed(
    category: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ApiEnvelope[list[LogFeedItem]]:
    svc = LogService(db)
    return ok(svc.get_feed(category, limit))
