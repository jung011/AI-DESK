"""attachment repository — t_ai_message_attachment 접근."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.messages.attachment_models import MessageAttachment


class AttachmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def insert(self, a: MessageAttachment) -> MessageAttachment:
        self.db.add(a)
        self.db.flush()
        return a

    def find_by_id(self, attachment_id: str) -> MessageAttachment | None:
        return self.db.execute(
            select(MessageAttachment).where(MessageAttachment.attachment_id == attachment_id)
        ).scalar_one_or_none()

    def list_by_message_id(self, message_id: str) -> list[MessageAttachment]:
        return list(
            self.db.execute(
                select(MessageAttachment)
                .where(MessageAttachment.message_id == message_id)
                .order_by(MessageAttachment.created_at)
            ).scalars()
        )

    def list_by_message_ids(self, message_ids: list[str]) -> dict[str, list[MessageAttachment]]:
        """여러 message_id 한 번에 — list endpoint N+1 회피."""
        if not message_ids:
            return {}
        rows = list(
            self.db.execute(
                select(MessageAttachment)
                .where(MessageAttachment.message_id.in_(message_ids))
                .order_by(MessageAttachment.created_at)
            ).scalars()
        )
        result: dict[str, list[MessageAttachment]] = {}
        for r in rows:
            if r.message_id is None:
                continue
            result.setdefault(r.message_id, []).append(r)
        return result

    def link_to_message(
        self,
        attachment_ids: list[str],
        message_id: str,
        owner_agent_id: str,
    ) -> int:
        """upload 후 아직 message 에 link 안 된 attachment 들을 message_id 에 attach.

        보안 — owner_agent_id 가 일치하고 message_id 가 NULL 인 row 만. 다른 agent 의
        attachment 를 도용하거나 이미 attached 된 것을 재사용 못 함.
        """
        if not attachment_ids:
            return 0
        stmt = (
            update(MessageAttachment)
            .where(
                MessageAttachment.attachment_id.in_(attachment_ids),
                MessageAttachment.owner_agent_id == owner_agent_id,
                MessageAttachment.message_id.is_(None),
            )
            .values(message_id=message_id)
        )
        result = self.db.execute(stmt)
        return result.rowcount or 0
