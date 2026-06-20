"""desktop router — /api/desktop/*. Spring DesktopController 와 1:1.

- POST /api/desktop/local-info : helper 30초 reporter 수신
- GET  /api/desktop/events     : helper / dashboard 의 SSE subscribe (메시지 broker 재사용)
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.response import ApiEnvelope, ok
from app.core.database import get_db
from app.desktop.schemas import DesktopLocalInfoRq, DesktopLocalInfoRs
from app.desktop.service import DesktopService
from app.messages.sse import broker

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "desktop", "status": "ok"}


@router.post("/local-info", response_model=ApiEnvelope[DesktopLocalInfoRs])
async def upload_local_info(
    body: DesktopLocalInfoRq, db: Session = Depends(get_db)
) -> ApiEnvelope[DesktopLocalInfoRs]:
    """helper reporter 가 30초 마다 호출 — workspaces + tmux sessions snapshot.

    인증 없음 — 1단계 PoC. M6 단계에서 JWT 인증 추가 예정.
    """
    svc = DesktopService(db)
    return ok(svc.apply_local_info(body))


@router.get("/events")
async def events() -> StreamingResponse:
    """SSE channel — helper / dashboard 가 subscribe. messages 의 broker 재사용 (단일 채널).

    이벤트 타입:
    - `event: connected` — 초기
    - `event: message.created` — 새 메시지
    - `: keepalive` (15초)
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
