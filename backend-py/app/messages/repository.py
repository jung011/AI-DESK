"""messages DB 접근 — Spring MessageMapper 와 1:1 (핵심 query)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.orm import Session

from app.messages.models import Message


class MessageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def insert(self, msg: Message) -> Message:
        self.db.add(msg)
        self.db.flush()
        return msg

    def find_by_id(self, message_id: str) -> Message | None:
        return self.db.execute(
            select(Message).where(Message.message_id == message_id)
        ).scalar_one_or_none()

    def list_for_agent(
        self,
        agent_id: str,
        direction: str = "all",
        with_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> tuple[list[Message], bool]:
        """direction = 'in' / 'out' / 'all'.

        Returns (rows, has_more) — has_more = limit + 1 패턴.
        """
        stmt = select(Message)
        if direction == "in":
            stmt = stmt.where(Message.to_agent_id == agent_id)
        elif direction == "out":
            stmt = stmt.where(Message.from_agent_id == agent_id)
        else:
            stmt = stmt.where(or_(Message.from_agent_id == agent_id, Message.to_agent_id == agent_id))
        if with_id:
            stmt = stmt.where(
                or_(
                    and_(Message.from_agent_id == agent_id, Message.to_agent_id == with_id),
                    and_(Message.from_agent_id == with_id, Message.to_agent_id == agent_id),
                )
            )
        if status:
            stmt = stmt.where(Message.status == status)
        stmt = stmt.order_by(desc(Message.created_at)).limit(limit + 1)

        rows = list(self.db.execute(stmt).scalars())
        has_more = len(rows) > limit
        return (rows[:limit], has_more)

    def count_recent_from(self, from_agent_id: str, seconds: int = 60) -> int:
        """rate limit 검사용 — 최근 N초 안 from_agent_id 발신 수."""
        threshold = datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)
        return self.db.execute(
            select(func.count(Message.sn)).where(
                Message.from_agent_id == from_agent_id,
                Message.created_at >= threshold,
            )
        ).scalar_one()

    def count_unread_for_to(self, agent_id: str) -> int:
        """대상이 본인이고 read_at 미설정 인 메시지 수."""
        return self.db.execute(
            select(func.count(Message.sn)).where(
                Message.to_agent_id == agent_id,
                Message.read_at.is_(None),
                Message.status.in_(["sent", "delivered"]),
            )
        ).scalar_one()

    def list_unread_by_from(self, agent_id: str) -> list[tuple[str, int]]:
        """발신자(from)별 미확인 수 — UnreadCountRsVo.byAgent."""
        stmt = (
            select(Message.from_agent_id, func.count(Message.sn))
            .where(
                Message.to_agent_id == agent_id,
                Message.read_at.is_(None),
                Message.status.in_(["sent", "delivered"]),
            )
            .group_by(Message.from_agent_id)
        )
        return [(row[0], int(row[1])) for row in self.db.execute(stmt).all()]

    def mark_read(self, message_id: str, agent_id: str) -> int:
        """to_agent_id == agent_id 일 때만 read_at 마킹 (다른 사용자 가 읽음 처리 차단)."""
        result = self.db.execute(
            update(Message)
            .where(
                Message.message_id == message_id,
                Message.to_agent_id == agent_id,
                Message.read_at.is_(None),
            )
            .values(read_at=datetime.now(tz=timezone.utc))
        )
        return result.rowcount

    def ack_delivered(self, message_id: str) -> int:
        """status='sent' 이면 'delivered' + delivered_at. 다른 status 면 변화 없음 (멱등)."""
        result = self.db.execute(
            update(Message)
            .where(
                Message.message_id == message_id,
                Message.status == "sent",
            )
            .values(status="delivered", delivered_at=datetime.now(tz=timezone.utc))
        )
        return result.rowcount

    def mark_sent(self, message_id: str) -> None:
        self.db.execute(
            update(Message).where(Message.message_id == message_id).values(status="sent")
        )

    def mark_failed(self, message_id: str, reason: str) -> None:
        self.db.execute(
            update(Message)
            .where(Message.message_id == message_id)
            .values(status="failed", error_reason=reason)
        )
