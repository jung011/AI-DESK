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
from app.logs.models import ClientEvent  # noqa: F401 — alembic create_all 시 model 등록
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


@router.post("/logs/client-event", response_model=ApiEnvelope[str])
async def record_client_event(
    request: Request,
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[str]:
    """frontend critical 진단 event → DB 영구 저장. pod replace 무관.

    저장 대상 = nav-debug 의 location.* / keydown:refresh / beforeunload:snapshot /
    window:error 같은 *원인 모를 reload / logout* 사고 추적 event. K8s stdout log
    pod replace 시 손실 사고 회피용.

    사용자 frontend 가 navigator.sendBeacon() 로 호출 — page unload 도중도 살림.
    body = {"event": "location:reload", "route": "/dashboard", "data": {...}}
    """
    import json
    import uuid as _uuid

    from app.logs.models import ClientEvent

    try:
        raw = await request.body()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        payload = {}

    event_type = str(payload.get("event") or "")[:50]
    if not event_type:
        return ok("skipped")  # event_type 없으면 무시

    route = (payload.get("route") or "")[:500]
    data_obj = payload.get("data")
    data_json = json.dumps(data_obj, ensure_ascii=False, default=str)[:5000] if data_obj is not None else None
    ua = (request.headers.get("user-agent") or "")[:500]

    try:
        row = ClientEvent(
            event_id=str(_uuid.uuid4()),
            account_sn=user.account_sn if user else None,
            event_type=event_type,
            route=route or None,
            data=data_json,
            user_agent=ua or None,
        )
        db.add(row)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        client_log.warning("[client-event] DB insert failed: %s event=%s", e, event_type)
        return ok("db-error")

    return ok("ok")
