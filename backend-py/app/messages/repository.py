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

    def aggregate_wiring(self, window_min: int = 30) -> list[tuple[str, str, int, datetime]]:
        """최근 window_min 분 의 agent pair (from, to) 별 메시지 수 + 가장 최근 timestamp.

        대시보드 wiring view 용 — 활발한 대화 쌍 visualize.
        반환: [(fromAgentId, toAgentId, messageCount, lastAt), ...]
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=window_min)
        stmt = (
            select(
                Message.from_agent_id,
                Message.to_agent_id,
                func.count(Message.message_id).label("count"),
                func.max(Message.created_at).label("last_at"),
            )
            .where(Message.created_at >= cutoff)
            .group_by(Message.from_agent_id, Message.to_agent_id)
            .order_by(desc("count"))
        )
        return [(r.from_agent_id, r.to_agent_id, r.count, r.last_at) for r in self.db.execute(stmt).all()]

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

        with_id 박혀있으면 *contact-centric* 모드 — partner (with_id) 가 관여한
        모든 메시지 반환 ([[project-user-entity-model]] 룰: 채팅창은 partner 관여
        모든 메시지 표시). 예: test ↔ test2 통신도 test2 채팅창에 보여야.
        with_id 없으면 *agent in/out* 모드 — agent_id 의 메시지만.
        Returns (rows, has_more) — has_more = limit + 1 패턴.
        """
        stmt = select(Message)
        if with_id:
            # contact-centric — partner 가 관여한 모든 메시지 (agent_id filter 안 함)
            stmt = stmt.where(or_(Message.from_agent_id == with_id, Message.to_agent_id == with_id))
        elif direction == "in":
            stmt = stmt.where(Message.to_agent_id == agent_id)
        elif direction == "out":
            stmt = stmt.where(Message.from_agent_id == agent_id)
        else:
            stmt = stmt.where(or_(Message.from_agent_id == agent_id, Message.to_agent_id == agent_id))
        if status:
            stmt = stmt.where(Message.status == status)
        stmt = stmt.order_by(desc(Message.created_at)).limit(limit + 1)

        rows = list(self.db.execute(stmt).scalars())
        has_more = len(rows) > limit
        return (rows[:limit], has_more)

    def count_recent_from(self, from_agent_id: str, seconds: int = 60) -> int:  # noqa: D401

        """rate limit 검사용 — 최근 N초 안 from_agent_id 발신 수."""
        threshold = datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)
        return self.db.execute(
            select(func.count(Message.message_id)).where(
                Message.from_agent_id == from_agent_id,
                Message.created_at >= threshold,
            )
        ).scalar_one()

    def count_unread_for_to(self, agent_id: str) -> int:
        """대상이 본인이고 read_at 미설정 인 메시지 수."""
        return self.db.execute(
            select(func.count(Message.message_id)).where(
                Message.to_agent_id == agent_id,
                Message.read_at.is_(None),
                Message.status.in_(["sent", "delivered"]),
            )
        ).scalar_one()

    def list_unread_by_from(self, agent_id: str) -> list[tuple[str, int]]:
        """발신자(from)별 미확인 수 — UnreadCountRsVo.byAgent."""
        stmt = (
            select(Message.from_agent_id, func.count(Message.message_id))
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

    # ---- conversations / audit / partners ----

    def list_conversations_for(self, agent_id: str) -> list[tuple[str, str | None, datetime, str, str]]:
        """대화 partner 목록 — (partner_agent_id, last_message_id, last_activity_at, last_direction, last_content).

        partner = from 또는 to 의 *나 자신 아닌 쪽*. 각 partner 별 최근 1건.
        """
        # SQLAlchemy 의 window function 사용보다 단순: agent 의 모든 메시지 가져와서 Python 에서 그룹화.
        # PoC 규모 (~수천 row) 면 in-memory 처리 충분. 운영 규모 커지면 SQL window function 으로 교체.
        stmt = select(Message).where(
            or_(Message.from_agent_id == agent_id, Message.to_agent_id == agent_id)
        ).order_by(desc(Message.created_at))
        rows = list(self.db.execute(stmt).scalars())

        seen: dict[str, tuple[str, datetime, str, str]] = {}
        for m in rows:
            partner = m.to_agent_id if m.from_agent_id == agent_id else m.from_agent_id
            if partner in seen:
                continue
            direction = "out" if m.from_agent_id == agent_id else "in"
            seen[partner] = (m.message_id, m.created_at, direction, m.content)
        return [(p, *v) for p, v in seen.items()]  # type: ignore[misc]

    def count_unread_with_partner(self, agent_id: str, partner_agent_id: str) -> int:
        return self.db.execute(
            select(func.count(Message.message_id)).where(
                Message.to_agent_id == agent_id,
                Message.from_agent_id == partner_agent_id,
                Message.read_at.is_(None),
                Message.status.in_(["sent", "delivered"]),
            )
        ).scalar_one()

    def select_audit(
        self,
        status: str | None,
        from_agent_id: str | None,
        to_agent_id: str | None,
        q: str | None,
        limit: int,
    ) -> tuple[list[Message], bool]:
        """감사 로그 — 모든 메시지 시간 역순 + 옵션 필터. limit+1 패턴."""
        stmt = select(Message)
        if status:
            stmt = stmt.where(Message.status == status)
        if from_agent_id:
            stmt = stmt.where(Message.from_agent_id == from_agent_id)
        if to_agent_id:
            stmt = stmt.where(Message.to_agent_id == to_agent_id)
        if q:
            stmt = stmt.where(Message.content.ilike(f"%{q}%"))
        stmt = stmt.order_by(desc(Message.created_at)).limit(limit + 1)
        rows = list(self.db.execute(stmt).scalars())
        has_more = len(rows) > limit
        return (rows[:limit], has_more)

    def list_recent_partners(self, agent_id: str, max_partners: int = 10) -> list[str]:
        """agents.realtime 의 partners — 최근 대화 partner agent_id list (중복 제거 순서 보존)."""
        stmt = select(Message).where(
            or_(Message.from_agent_id == agent_id, Message.to_agent_id == agent_id)
        ).order_by(desc(Message.created_at)).limit(100)
        rows = list(self.db.execute(stmt).scalars())
        partners: list[str] = []
        seen: set[str] = set()
        for m in rows:
            partner = m.to_agent_id if m.from_agent_id == agent_id else m.from_agent_id
            if partner in seen:
                continue
            seen.add(partner)
            partners.append(partner)
            if len(partners) >= max_partners:
                break
        return partners
