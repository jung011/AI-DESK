"""logs router — /api/action-logs + /api/logs + /api/logs/client. Spring LogController 와 1:1.

router prefix = /api (main.py 에서 mount).
"""
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import current_user, optional_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, ok
from app.core.database import get_db
from app.logs.schemas import ActionLogCreateRq, ClientLogRq, LogFeedItem
from app.logs.service import LogService

router = APIRouter()
client_log = logging.getLogger("app.client")


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
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[list[LogFeedItem]]:
    """sameUser 격리 박힌 통합 로그 feed — 그 user 의 agent 가 발신/수신한 거 만 반환."""
    svc = LogService(db)
    return ok(svc.get_feed(category, limit, account_sn=user.account_sn))


@router.post("/logs/client", response_model=ApiEnvelope[str])
async def record_client_log(
    body: ClientLogRq,
    request: Request,
    user: AuthenticatedUser | None = Depends(optional_user),
) -> ApiEnvelope[str]:
    """frontend 의 사고/진단 로그 적재. backend application logger 의 'app.client' channel.

    K8s stdout 에 모이므로 별도 DB schema 없이도 진단 가능. 옛 console 손실 사고
    ([[feedback-browser-debug-persist]]) 해소 — 미래 사고 시 backend log 직접 조회.
    """
    # 'log' / 'debug' 는 Python logger 의 .log(level, msg, ...) 시그니처와 충돌 — 첫
    # 인자 가 level int 박혀야 하는데 우리는 msg 박음 → TypeError → 500. normalize.
    level = (body.level or "warn").lower()
    if level in ("log", "debug"):
        level = "info"
    log_fn = getattr(client_log, level, client_log.warning)
    log_fn(
        "[client-log] msg=%s user=%s route=%s ua=%s data=%s",
        body.msg,
        user.login_id if user else "anonymous",
        body.route or "-",
        (request.headers.get("user-agent") or "-")[:200],
        body.data,
    )
    return ok("ok")
