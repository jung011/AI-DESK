"""agents router — /api/agents/*. Spring AgentController 와 1:1.

cross-user / channel-aware 권한 필터는 messages 도메인 포팅 turn 에 합쳐 완성.
지금은 dashboard cookie 인증 호출 = sameUser 만.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.schemas import (
    AgentCreateRq,
    AgentItem,
    AgentListRs,
    AgentRealtimeItem,
    AgentStatusUpdateRq,
)
from app.agents.service import AgentService
from app.auth.deps import current_user, optional_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, fail, ok
from app.core.database import get_db

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "agents", "status": "ok"}


@router.get("", response_model=ApiEnvelope[AgentListRs])
async def list_agents(
    status: str | None = None,
    callerAgentId: str | None = None,  # noqa: N803 — frontend query param 이름 유지
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[AgentListRs]:
    """sameUser agent 목록 + (callerAgentId 동봉 시) channel-aware filter."""
    svc = AgentService(db)
    return ok(svc.get_list(user.account_sn, status, callerAgentId))


@router.get("/realtime", response_model=ApiEnvelope[list[AgentRealtimeItem]])
async def realtime(
    db: Session = Depends(get_db),
    _user: AuthenticatedUser | None = Depends(optional_user),
) -> ApiEnvelope[list[AgentRealtimeItem]]:
    """외부 시각화 BE 호출. partners 는 messages 포팅 후 채워짐."""
    svc = AgentService(db)
    return ok(svc.get_realtime())


@router.get("/{agent_id}", response_model=ApiEnvelope[AgentItem])
async def detail(
    agent_id: str,
    _user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[AgentItem]:
    svc = AgentService(db)
    item = svc.detail(agent_id)
    if item is None:
        return fail(404, "agent not found")  # type: ignore[return-value]
    return ok(item)


@router.post("", response_model=ApiEnvelope[AgentItem])
async def create(
    body: AgentCreateRq,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[AgentItem]:
    svc = AgentService(db)
    item = svc.create(user.account_sn, body)
    if item is None:
        return fail(500, "register failed")  # type: ignore[return-value]
    return ok(item)


@router.delete("/{agent_id}", response_model=ApiEnvelope[None])
async def delete(
    agent_id: str,
    _user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    svc = AgentService(db)
    ok_ = svc.delete(agent_id)
    if not ok_:
        return fail(404, "agent not found")  # type: ignore[return-value]
    return ok(None)


@router.post("/{agent_id}/status", response_model=ApiEnvelope[None])
async def update_status(
    agent_id: str,
    body: AgentStatusUpdateRq,
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """helper / hook 이 호출. Spring 처럼 permitAll (인증 X) — agent_id 자체가 식별.

    body.status = None 또는 빈 문자열 시 404 처리 (Spring 행위와 동일).
    """
    svc = AgentService(db)
    ok_ = svc.update_status(agent_id, body.status)
    if not ok_:
        return fail(404, "agent not found")  # type: ignore[return-value]
    return ok(None)
