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


@router.get("/wiring", response_model=ApiEnvelope[dict])
async def wiring(
    windowMin: int = 30,  # noqa: N803 — frontend query param 유지
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[dict]:
    """대시보드 wiring view — *호출 user 의 agent 만* 의 pair 대화 통계.

    옛 = 인증 없음 + filter 없음 → 다른 user 의 agent 대화 graph 노출 사고.
    fix = current_user + account_sn 의 own agent 만.
    """
    from app.messages.repository import MessageRepository
    repo = MessageRepository(db)
    rows = repo.aggregate_wiring(window_min=windowMin, account_sn=user.account_sn)
    return ok({
        "links": [
            {"fromAgentId": f, "toAgentId": t, "count": c, "lastAt": last.isoformat()}
            for f, t, c, last in rows
        ],
        "windowMin": windowMin,
    })


@router.get("", response_model=ApiEnvelope[AgentListRs])
async def list_agents(
    status: str | None = None,
    callerAgentId: str | None = None,  # noqa: N803 — frontend query param 이름 유지
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[AgentListRs]:
    """Spring `/api/agents/**` permitAll — aidesk-channel mcp 가 쿠키 없이 호출.

    인증 호출 = dashboard (cookie). 비인증 호출 = mcp (callerAgentId fallback).
    """
    svc = AgentService(db)
    account_sn = user.account_sn if user else None
    return ok(svc.get_list(account_sn, status, callerAgentId))


@router.get("/realtime", response_model=ApiEnvelope[list[AgentRealtimeItem]])
async def realtime(
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[list[AgentRealtimeItem]]:
    """외부 시각화 BE 호출. sameUser 격리 — caller 의 own agent 만.

    옛 = optional + 전체. fix = current_user + account_sn filter. 외부 시각화 BE 가
    이 endpoint 사용하면 cookie 또는 bearer 필요. by-design public 이 아닌 user-scoped.
    """
    svc = AgentService(db)
    return ok(svc.get_realtime(account_sn=user.account_sn))


@router.get("/{agent_id}", response_model=ApiEnvelope[AgentItem])
async def detail(
    agent_id: str,
    callerAgentId: str | None = None,  # noqa: N803 — mcp 가 sameUser 검증용 query
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[AgentItem]:
    """agent detail — caller 의 own user 의 agent 만.

    옛 = 인증 optional + filter 없음 → 다른 user agent 노출 사고.
    fix = caller 가 owner 이면 OK, mcp 의 callerAgentId 도 owner 매칭 검증.
    list_agents 의 동일 패턴 정합.
    """
    svc = AgentService(db)
    item = svc.detail(agent_id)
    if item is None:
        return fail(404, "agent not found")  # type: ignore[return-value]
    # sameUser 검증
    from app.agents.repository import AgentRepository
    agent_repo = AgentRepository(db)
    target = agent_repo.find_by_agent_id_any_owner(agent_id)
    target_owner = target.owner_account_sn if target else None
    caller_sn: int | None = None
    if user is not None:
        caller_sn = user.account_sn
    elif callerAgentId:
        caller = agent_repo.find_by_agent_id_any_owner(callerAgentId)
        if caller is not None:
            caller_sn = caller.owner_account_sn
    if caller_sn is None or target_owner != caller_sn:
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
    callerAgentId: str | None = None,  # noqa: N803 — mcp / helper 가 sameUser 검증용
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """helper / hook 이 호출. sameUser 격리 — caller 가 owner 인 agent 만 status 변경.

    옛 = permitAll + 검증 없음 = 다른 user agent sabotage 가능. fix = callerAgentId
    query 또는 cookie user 의 account_sn 매칭. helper 가 박는 호출은 같은 mac 의 agent
    들이므로 owner 매칭. body.status = None 또는 빈 문자열 시 404.
    """
    from app.agents.repository import AgentRepository
    agent_repo = AgentRepository(db)
    target = agent_repo.find_by_agent_id_any_owner(agent_id)
    target_owner = target.owner_account_sn if target else None
    caller_sn: int | None = None
    if user is not None:
        caller_sn = user.account_sn
    elif callerAgentId:
        caller = agent_repo.find_by_agent_id_any_owner(callerAgentId)
        if caller is not None:
            caller_sn = caller.owner_account_sn
    if caller_sn is None or target_owner != caller_sn:
        return fail(404, "agent not found")  # type: ignore[return-value]
    svc = AgentService(db)
    ok_ = svc.update_status(agent_id, body.status)
    if not ok_:
        return fail(404, "agent not found")  # type: ignore[return-value]
    return ok(None)
