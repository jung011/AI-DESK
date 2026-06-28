"""tasks router — /api/tasks/* + /api/agents/{id}/tasks.

`/api/agents/{id}/tasks` GET/POST 는 옛 agents 도메인의 path 와 정합 — agent 별 task list.
`/api/tasks/*` 는 task lifecycle (start / complete / cancel / list_recent).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import current_user, optional_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, fail, ok
from app.core.database import get_db
from app.messages.caller import resolve_caller_account_sn
from app.tasks.schemas import TaskCompleteRq, TaskCreateRq, TaskItem, TaskListRs
from app.tasks.service import AiTaskService

router = APIRouter()


@router.get("/recent", response_model=ApiEnvelope[TaskListRs])
async def list_recent(
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[TaskListRs]:
    """대시보드 상단 패널 — *호출 user 가 박은* 최근 task.

    sameUser 격리 — 다른 user (리키2 등) 의 task 는 안 보임. 옛 optional_user +
    필터 없는 list_recent 가 *모든 user task 노출* 보안 사고 fix. agents/list 의
    sameUser 격리 패턴 정합.
    """
    svc = AiTaskService(db)
    return ok(svc.list_recent(user.account_sn))


@router.post("", response_model=ApiEnvelope[TaskItem])
async def create_task(
    body: TaskCreateRq,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[TaskItem]:
    svc = AiTaskService(db)
    item = svc.create(user.account_sn, body)
    if item is None:
        return fail(404, "agent not found")  # type: ignore[return-value]
    return ok(item)


@router.post("/{task_id}/start", response_model=ApiEnvelope[None])
async def start_task(
    task_id: str,
    callerAgentId: str | None = Query(default=None),  # noqa: N803
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """mcp tool task_start. caller = cookie user 또는 callerAgentId 의 owner.
    sameUser 격리 — task 의 requester != caller 면 404. spoofing 차단.
    """
    caller_sn = resolve_caller_account_sn(db, user, callerAgentId)
    svc = AiTaskService(db)
    ok_ = svc.start(task_id, caller_account_sn=caller_sn)
    if not ok_:
        return fail(404, "task not found")  # type: ignore[return-value]
    return ok(None)


@router.post("/{task_id}/complete", response_model=ApiEnvelope[None])
async def complete_task(
    task_id: str,
    body: TaskCompleteRq,
    callerAgentId: str | None = Query(default=None),  # noqa: N803
    user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """mcp tool task_complete. sameUser 격리 — task requester == caller 매칭."""
    caller_sn = resolve_caller_account_sn(db, user, callerAgentId)
    svc = AiTaskService(db)
    ok_ = svc.complete(task_id, body.result, caller_account_sn=caller_sn)
    if not ok_:
        return fail(404, "task not found")  # type: ignore[return-value]
    return ok(None)


@router.post("/{task_id}/cancel", response_model=ApiEnvelope[None])
async def cancel_task(
    task_id: str,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """사용자 수동 cancel. sameUser 격리 — caller user.account_sn == requester."""
    svc = AiTaskService(db)
    ok_ = svc.cancel(task_id, caller_account_sn=user.account_sn)
    if not ok_:
        return fail(404, "task not found")  # type: ignore[return-value]
    return ok(None)
