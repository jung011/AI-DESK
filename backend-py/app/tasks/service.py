"""task business logic."""
import logging
import uuid

from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.messages.attachment_repository import AttachmentRepository
from app.messages.sse import broker
from app.tasks.models import AiTask
from app.tasks.repository import AiTaskRepository
from app.tasks.schemas import (
    TaskAttachmentItem,
    TaskCreateRq,
    TaskItem,
    TaskListRs,
)

log = logging.getLogger(__name__)


class AiTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AiTaskRepository(db)
        self.agent_repo = AgentRepository(db)
        self.att_repo = AttachmentRepository(db)

    def create(self, requester_account_sn: int | None, body: TaskCreateRq) -> TaskItem | None:
        agent = self.agent_repo.find_by_agent_id(body.agent_id)
        if agent is None:
            return None
        task = AiTask(
            task_id=str(uuid.uuid4()),
            agent_id=body.agent_id,
            content=body.content,
            status="todo",
            requester_account_sn=requester_account_sn,
        )
        self.repo.insert(task)
        # 첨부 link — message_id 와 같은 path 의 task_id 박음
        if body.attachment_ids:
            self.att_repo.link_to_task(body.attachment_ids, task.task_id)
        self.db.commit()
        self.db.refresh(task)
        broker.publish(
            "agent.task.changed",
            {"event": "created", "taskId": task.task_id, "agentId": task.agent_id},
        )
        return self._to_item(task)

    def list_for_agent(self, agent_id: str) -> TaskListRs:
        rows = self.repo.list_by_agent(agent_id)
        return TaskListRs(items=[self._to_item(t) for t in rows])

    def list_recent(self) -> TaskListRs:
        rows = self.repo.list_recent()
        return TaskListRs(items=[self._to_item(t) for t in rows])

    def start(self, task_id: str) -> bool:
        n = self.repo.mark_started(task_id)
        self.db.commit()
        ok = n > 0
        if ok:
            broker.publish("agent.task.changed", {"event": "started", "taskId": task_id})
        return ok

    def complete(self, task_id: str, result: str | None) -> bool:
        n = self.repo.mark_completed(task_id, result)
        self.db.commit()
        ok = n > 0
        if ok:
            broker.publish("agent.task.changed", {"event": "completed", "taskId": task_id})
        return ok

    def cancel(self, task_id: str) -> bool:
        n = self.repo.mark_status(task_id, "canceled")
        self.db.commit()
        ok = n > 0
        if ok:
            broker.publish("agent.task.changed", {"event": "canceled", "taskId": task_id})
        return ok

    def _to_item(self, t: AiTask) -> TaskItem:
        agent = self.agent_repo.find_by_agent_id(t.agent_id)
        att_rows = self.att_repo.find_by_task_id(t.task_id)
        return TaskItem(
            task_id=t.task_id,
            agent_id=t.agent_id,
            agent_name=agent.agent_name if agent else None,
            content=t.content,
            status=t.status,
            result=t.result,
            created_at=t.created_at,
            started_at=t.started_at,
            completed_at=t.completed_at,
            attachments=[
                TaskAttachmentItem(
                    attachment_id=a.attachment_id,
                    original_filename=a.original_filename,
                    content_type=a.content_type,
                    size_bytes=a.size_bytes,
                )
                for a in att_rows
            ],
        )
