"""messages business logic — Spring MessageService 핵심 6 endpoint.

이번 turn 포팅:
- send (create) — 정책 검사 + insert + sent 마킹
- detail
- list (in/out/all + with_id 대화 partner 필터)
- unread_count
- mark_read
- ack_delivered

다음 turn (별도):
- broadcast / conversations / audit
- SSE push (broadcast 채널)
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.messages.models import Message
from app.messages.policy import PolicyResult, check_send
from app.messages.repository import MessageRepository
from app.messages.schemas import (
    AgentUnread,
    MessageCreateRq,
    MessageItem,
    MessageListRs,
    UnreadCountRs,
)

log = logging.getLogger(__name__)


class MessageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = MessageRepository(db)
        self.agent_repo = AgentRepository(db)

    # ---- send (create) ----

    def create(self, body: MessageCreateRq) -> MessageItem:
        """1:1 메시지 송신. 정책 위반 시 status='failed' + error_reason 로 row 보존 (audit)."""
        from_id = body.from_agent_id
        to_id = body.to_agent_id
        if from_id == to_id:
            return self._save_failed(body, "self-message 차단")

        sender = self.agent_repo.find_by_agent_id_any_owner(from_id)
        if sender is None:
            return self._save_failed(body, "발신 agent 없음")
        receiver = self.agent_repo.find_by_agent_id_any_owner(to_id)
        if receiver is None:
            return self._save_failed(body, "수신 agent 없음")

        parent: Message | None = None
        if body.reply_to_message_id:
            parent = self.repo.find_by_id(body.reply_to_message_id)
            if parent is None:
                return self._save_failed(body, "reply_to_message_id 없음")

        result: PolicyResult = check_send(sender, receiver, parent, self.repo)
        if not result.accepted:
            log.info(
                "policy reject: from=%s to=%s reason=%s",
                sender.agent_name, receiver.agent_name, result.reason,
            )
            return self._save_failed(body, result.reason, parent=parent)

        msg = Message(
            message_id=str(uuid.uuid4()),
            from_agent_id=from_id,
            to_agent_id=to_id,
            content=body.content,
            reply_to_message_id=body.reply_to_message_id,
            root_message_id=(parent.root_message_id or parent.message_id) if parent else None,
            hop_count=(parent.hop_count or 0) + 1 if parent else 1,
            status="sent",
            retry_count=0,
        )
        self.repo.insert(msg)
        self.db.commit()
        self.db.refresh(msg)
        return self._enrich(msg, sender_name=sender.agent_name, receiver_name=receiver.agent_name)

    def _save_failed(
        self,
        body: MessageCreateRq,
        reason: str,
        parent: Message | None = None,
    ) -> MessageItem:
        """정책 / 사전 검사 거절 — failed row 보존 + audit. caller 에게 응답에 reason 노출."""
        msg = Message(
            message_id=str(uuid.uuid4()),
            from_agent_id=body.from_agent_id,
            to_agent_id=body.to_agent_id,
            content=body.content,
            reply_to_message_id=body.reply_to_message_id,
            root_message_id=(parent.root_message_id or parent.message_id) if parent else None,
            hop_count=((parent.hop_count or 0) + 1) if parent else 1,
            status="failed",
            error_reason=reason,
            retry_count=0,
        )
        self.repo.insert(msg)
        self.db.commit()
        self.db.refresh(msg)
        return self._enrich(msg)

    # ---- detail ----

    def detail(self, message_id: str) -> MessageItem | None:
        msg = self.repo.find_by_id(message_id)
        if msg is None:
            return None
        return self._enrich(msg)

    # ---- list ----

    def get_list(
        self,
        agent_id: str,
        direction: str = "all",
        with_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> MessageListRs:
        rows, has_more = self.repo.list_for_agent(agent_id, direction, with_id, status, limit)
        items = [self._enrich(r) for r in rows]
        return MessageListRs(items=items, has_more=has_more)

    # ---- unread count ----

    def get_unread_count(self, agent_id: str | None) -> UnreadCountRs:
        if not agent_id:
            return UnreadCountRs(total_unread=0, by_agent=[])
        total = self.repo.count_unread_for_to(agent_id)
        by_from = self.repo.list_unread_by_from(agent_id)
        result = []
        for from_id, n in by_from:
            sender = self.agent_repo.find_by_agent_id_any_owner(from_id)
            result.append(
                AgentUnread(
                    agent_id=from_id,
                    agent_name=sender.agent_name if sender else from_id,
                    unread=n,
                )
            )
        return UnreadCountRs(total_unread=total, by_agent=result)

    # ---- mark read / ack ----

    def mark_read(self, message_id: str, agent_id: str) -> bool:
        n = self.repo.mark_read(message_id, agent_id)
        self.db.commit()
        return n > 0

    def ack_delivered(self, message_id: str) -> None:
        self.repo.ack_delivered(message_id)
        self.db.commit()

    # ---- helper ----

    def _enrich(
        self,
        msg: Message,
        sender_name: str | None = None,
        receiver_name: str | None = None,
    ) -> MessageItem:
        """MessageItem 에 from/to agent_name 채워서 반환."""
        if sender_name is None:
            sender = self.agent_repo.find_by_agent_id_any_owner(msg.from_agent_id)
            sender_name = sender.agent_name if sender else None
        if receiver_name is None:
            receiver = self.agent_repo.find_by_agent_id_any_owner(msg.to_agent_id)
            receiver_name = receiver.agent_name if receiver else None
        item = MessageItem.model_validate(msg)
        item.from_agent_name = sender_name
        item.to_agent_name = receiver_name
        return item
