"""logs business logic — Spring LogService 핵심.

action log insert + 통합 feed (message + action 합쳐 시간 역순).
"""
import logging
import uuid

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.logs.models import ActionLog
from app.logs.schemas import ActionLogCreateRq, LogFeedItem
from app.messages.models import Message

log = logging.getLogger(__name__)


class LogService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.agent_repo = AgentRepository(db)

    def record_action(self, body: ActionLogCreateRq) -> str:
        log_id = str(uuid.uuid4())
        row = ActionLog(
            log_id=log_id,
            agent_id=body.agent_id,
            agent_name=body.agent_name,
            session_id=body.session_id,
            cwd=body.cwd,
            tool=body.tool,
            category=body.category,
            target=body.target,
            summary=body.summary,
        )
        self.db.add(row)
        self.db.commit()
        return log_id

    def get_feed(self, category: str | None = None, limit: int | None = None) -> list[LogFeedItem]:
        """message + action 합쳐 시간 역순. category filter 적용."""
        n = limit if (limit and 1 <= limit <= 500) else 100

        # action log
        stmt_a = select(ActionLog).order_by(desc(ActionLog.created_at), desc(ActionLog.sn)).limit(n)
        if category:
            stmt_a = select(ActionLog).where(ActionLog.category == category).order_by(
                desc(ActionLog.created_at), desc(ActionLog.sn)
            ).limit(n)
        actions = list(self.db.execute(stmt_a).scalars())

        # message — category=None 이거나 'message' 인 경우만
        messages: list[Message] = []
        if not category or category == "message":
            stmt_m = select(Message).order_by(desc(Message.created_at), desc(Message.sn)).limit(n)
            messages = list(self.db.execute(stmt_m).scalars())

        # 통합 + 시간 역순 + limit
        items: list[LogFeedItem] = []
        for a in actions:
            items.append(
                LogFeedItem(
                    type="action",
                    created_at=a.created_at,
                    category=a.category,
                    agent_id=a.agent_id,
                    agent_name=a.agent_name,
                    summary=a.summary,
                    target=a.target,
                )
            )
        for m in messages:
            sender = self.agent_repo.find_by_agent_id_any_owner(m.from_agent_id)
            items.append(
                LogFeedItem(
                    type="message",
                    created_at=m.created_at,
                    category="message",
                    agent_id=m.from_agent_id,
                    agent_name=sender.agent_name if sender else m.from_agent_id,
                    summary=m.content[:200] + ("…" if len(m.content) > 200 else ""),
                    target=m.to_agent_id,
                )
            )
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[:n]
