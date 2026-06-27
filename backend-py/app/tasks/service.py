"""task business logic."""
import logging
import uuid

from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.messages.attachment_repository import AttachmentRepository
from app.messages.schemas import MessageCreateRq
from app.messages.service import MessageService
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
        # 자동 push — 다음 todo task 가 있고 옛 in_progress 없으면 휴먼→AI 메시지 박음.
        self._push_next_to_agent(agent.agent_id, requester_account_sn)
        return self._to_item(task)

    def list_for_agent(self, agent_id: str) -> TaskListRs:
        rows = self.repo.list_by_agent(agent_id)
        items = [self._to_item(t) for t in rows]
        # [[feedback-rc50-readonly-commit-n-plus-1]] — read-only endpoint 도 implicit
        # transaction 종료 필요. autocommit=False 에서 commit 안 박으면 *idle in
        # transaction* 누적 → pool 고갈 사고 패턴.
        self.db.commit()
        return TaskListRs(items=items)

    def list_recent(self) -> TaskListRs:
        rows = self.repo.list_recent()
        items = [self._to_item(t) for t in rows]
        self.db.commit()
        return TaskListRs(items=items)

    def start(self, task_id: str) -> bool:
        n = self.repo.mark_started(task_id)
        self.db.commit()
        ok = n > 0
        if ok:
            broker.publish("agent.task.changed", {"event": "started", "taskId": task_id})
        return ok

    def complete(self, task_id: str, result: str | None) -> bool:
        task = self.repo.find_by_id(task_id)
        if task is None:
            return False
        n = self.repo.mark_completed(task_id, result)
        self.db.commit()
        ok = n > 0
        if ok:
            broker.publish("agent.task.changed", {"event": "completed", "taskId": task_id})
            # 다음 todo 자동 push
            self._push_next_to_agent(task.agent_id, task.requester_account_sn)
        return ok

    def cancel(self, task_id: str) -> bool:
        n = self.repo.mark_status(task_id, "canceled")
        self.db.commit()
        ok = n > 0
        if ok:
            broker.publish("agent.task.changed", {"event": "canceled", "taskId": task_id})
        return ok

    def _push_next_to_agent(self, agent_id: str, requester_account_sn: int | None) -> None:
        """다음 todo task 가 있고 옛 in_progress 가 없으면 휴먼→AI 메시지 박음.

        AI 가 메시지 받음 → identity prompt 에 박힌 *task lifecycle* 안내 따라
        task_start(task_id) mcp tool 호출 → 처리 → task_complete(task_id) 호출.

        from = 휴먼 entity (model='human', owner_account_sn 매칭). 휴먼 sender 는
        [[feedback-human-sender-policy-exempt]] 의 context 한도 차단 예외.
        """
        if requester_account_sn is None:
            return
        nxt = self.repo.list_next_todo_for_agent(agent_id)
        if nxt is None:
            return
        human = self.agent_repo.find_human_for_account(requester_account_sn)
        if human is None:
            log.warning(
                "task push: human entity for account_sn=%s not found — skip",
                requester_account_sn,
            )
            return
        att_rows = self.att_repo.find_by_task_id(nxt.task_id)
        # task 메시지 의 content — task_id 메타 + 명시 지시 박힘. AI 가 매 메시지 읽으니
        # mcp server instructions (시작 시 1회 로드) 보다 매 task 메시지 의 지시 가 더 정합.
        # AI 가 task_start / task_complete mcp tool 호출 path 학습.
        # 첨부는 content 의 GET URL 메타 (task_attachment row 와 message_attachment link
        # 분리 — owner ambiguity 회피). AI 가 URL 통해 직접 다운로드.
        att_lines = []
        for a in att_rows:
            size_kb = (a.size_bytes + 1023) // 1024
            att_lines.append(
                f"- {a.original_filename} ({size_kb}KB) — GET /api/attachments/{a.attachment_id}"
            )
        content = (
            f"[task:{nxt.task_id}]\n"
            f"{nxt.content}\n\n"
            f"⚠ 이 메시지는 사용자가 대시보드 task 패널에 박은 task 임. "
            f"처리 시작 시 mcp tool `task_start` (task_id=\"{nxt.task_id}\") 호출, "
            f"처리 완료 시 `task_complete` (task_id=\"{nxt.task_id}\", result=\"<완료 요약>\") 호출."
        )
        if att_lines:
            content += "\n\n첨부:\n" + "\n".join(att_lines)
        body = MessageCreateRq(
            fromAgentId=human.agent_id,
            toAgentId=agent_id,
            content=content,
            attachmentIds=[],
        )
        try:
            msg_svc = MessageService(self.db)
            msg_svc.create(body)
        except Exception as e:  # noqa: BLE001
            log.warning("task push: MessageService.create failed task=%s err=%s", nxt.task_id, e)
            # [[feedback-resource-cleanup-rule]] 1번 — 외부 자원 (DB) 처리 fail 시 rollback
            # 박지 않으면 transaction failed state 가 다음 query 막음. Depends(get_db) 의
            # session 도 명시 rollback 박는 게 안전 (옛 사고 패턴 차단).
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

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
