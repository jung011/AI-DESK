"""tasks router — /api/tasks/* + /api/agents/{id}/tasks.

`/api/agents/{id}/tasks` GET/POST 는 옛 agents 도메인의 path 와 정합 — agent 별 task list.
`/api/tasks/*` 는 task lifecycle (start / complete / cancel / list_recent).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import current_user, optional_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, fail, ok
from app.core.database import get_db
from app.tasks.schemas import TaskCompleteRq, TaskCreateRq, TaskItem, TaskListRs
from app.tasks.service import AiTaskService

router = APIRouter()


@router.get("/recent", response_model=ApiEnvelope[TaskListRs])
async def list_recent(
    _user: AuthenticatedUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[TaskListRs]:
    """대시보드 상단 패널 — 모든 agent 의 최근 task."""
    svc = AiTaskService(db)
    return ok(svc.list_recent())


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
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """mcp tool task_start 가 backend 에 보내는 endpoint. cookie-less (permitAll).

    AI 가 *task 받음 + 처리 시작* 시 호출. backend 가 status='in_progress' 마킹.
    """
    svc = AiTaskService(db)
    ok_ = svc.start(task_id)
    if not ok_:
        return fail(404, "task not found")  # type: ignore[return-value]
    return ok(None)


@router.post("/{task_id}/complete", response_model=ApiEnvelope[None])
async def complete_task(
    task_id: str,
    body: TaskCompleteRq,
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """mcp tool task_complete 가 호출. status='done' + result 박힘.

    backend 가 *다음 todo task* 자동 push (helper sse_consumer 통해).
    """
    svc = AiTaskService(db)
    ok_ = svc.complete(task_id, body.result)
    if not ok_:
        return fail(404, "task not found")  # type: ignore[return-value]
    return ok(None)


@router.post("/{task_id}/cancel", response_model=ApiEnvelope[None])
async def cancel_task(
    task_id: str,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    """사용자가 *수동 cancel* — Kanban UI 의 ✕ button."""
    _ = user  # 인증만 — 권한 filter 추가 후속
    svc = AiTaskService(db)
    ok_ = svc.cancel(task_id)
    if not ok_:
        return fail(404, "task not found")  # type: ignore[return-value]
    return ok(None)
