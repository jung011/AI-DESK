"""task repository."""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.tasks.models import AiTask


class AiTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def insert(self, task: AiTask) -> AiTask:
        self.db.add(task)
        self.db.flush()
        return task

    def find_by_id(self, task_id: str) -> AiTask | None:
        return self.db.execute(
            select(AiTask).where(AiTask.task_id == task_id)
        ).scalar_one_or_none()

    def list_by_agent(self, agent_id: str, limit: int = 100) -> list[AiTask]:
        return list(
            self.db.execute(
                select(AiTask)
                .where(AiTask.agent_id == agent_id)
                .order_by(AiTask.created_at.desc())
                .limit(limit)
            ).scalars()
        )

    def list_recent(self, limit: int = 100) -> list[AiTask]:
        """대시보드 상단 패널 — 모든 agent 의 최근 task."""
        return list(
            self.db.execute(
                select(AiTask)
                .order_by(AiTask.created_at.desc())
                .limit(limit)
            ).scalars()
        )

    def list_next_todo_for_agent(self, agent_id: str) -> AiTask | None:
        """*다음 push 대상* — agent 의 가장 오래된 todo. in_progress 가 있으면 None."""
        # 현재 in_progress 가 있으면 다음 push 안 함
        cur = self.db.execute(
            select(AiTask)
            .where(AiTask.agent_id == agent_id, AiTask.status == "in_progress")
            .limit(1)
        ).scalar_one_or_none()
        if cur is not None:
            return None
        return self.db.execute(
            select(AiTask)
            .where(AiTask.agent_id == agent_id, AiTask.status == "todo")
            .order_by(AiTask.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()

    def mark_started(self, task_id: str) -> int:
        n = self.db.execute(
            update(AiTask)
            .where(AiTask.task_id == task_id)
            .values(status="in_progress", started_at=datetime.now(timezone.utc))
        ).rowcount
        return n

    def mark_completed(self, task_id: str, result: str | None) -> int:
        n = self.db.execute(
            update(AiTask)
            .where(AiTask.task_id == task_id)
            .values(
                status="done",
                completed_at=datetime.now(timezone.utc),
                result=result,
            )
        ).rowcount
        return n

    def mark_status(self, task_id: str, status: str) -> int:
        n = self.db.execute(
            update(AiTask)
            .where(AiTask.task_id == task_id)
            .values(status=status)
        ).rowcount
        return n
