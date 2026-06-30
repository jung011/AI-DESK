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
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.messages.attachment_models import MessageAttachment
from app.messages.attachment_repository import AttachmentRepository
from app.messages.models import Message
from app.messages.policy import PolicyResult, check_send
from app.messages.repository import MessageRepository
from app.messages.schemas import (
    AgentUnread,
    AttachmentRef,
    ConversationItem,
    MessageBroadcastRq,
    MessageBroadcastRs,
    MessageCreateRq,
    MessageItem,
    MessageListRs,
    UnreadCountRs,
)
from app.messages.sse import broker
from app.messages.ws import ws_broker

log = logging.getLogger(__name__)


# Python event loop 의 weak reference 정책상 create_task 만 호출하면 GC 위험 — 강한 reference
# 안 잡으면 task 가 *중간에 cancel* 될 수 있음 (RuntimeWarning + 외부 AI 메시지 누락).
# done callback 으로 자동 discard — 무한 누적 방지.
_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro) -> None:
    """asyncio.create_task + strong reference + done callback discard."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _truncate(s: str | None, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "…"


class MessageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = MessageRepository(db)
        self.agent_repo = AgentRepository(db)
        self.attachment_repo = AttachmentRepository(db)

    # ---- send (create) ----

    def create(self, body: MessageCreateRq, caller_account_sn: int | None = None) -> MessageItem:
        """1:1 메시지 송신. 정책 위반 시 status='failed' + error_reason 로 row 보존 (audit).

        sameUser 격리 — caller_account_sn 박으면 fromAgentId 의 owner 가 caller 매칭
        검증. 다른 user 명의로 spoofing 차단.
        """
        from_id = body.from_agent_id
        to_id = body.to_agent_id
        if from_id == to_id:
            return self._save_failed(body, "self-message 차단")

        sender = self.agent_repo.find_by_agent_id_any_owner(from_id)
        if sender is None:
            return self._save_failed(body, "발신 agent 없음")
        if caller_account_sn is not None and sender.owner_account_sn != caller_account_sn:
            return self._save_failed(body, "fromAgent owner != caller — spoofing 차단")
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
        # 첨부 link — owner=sender 검증. ID mismatch / 이미 link 된 attachment 는 무시.
        if body.attachment_ids:
            self.attachment_repo.link_to_message(
                body.attachment_ids, msg.message_id, sender.agent_id
            )
        self.db.commit()
        self.db.refresh(msg)
        item = self._enrich(msg, sender_name=sender.agent_name, receiver_name=receiver.agent_name)

        # SSE push (helper sse_consumer) + WS push (frontend dashboard / 외부 AI mcp ws client)
        payload = item.model_dump(by_alias=True)
        payload["toTmuxSession"] = receiver.tmux_session
        # B Phase 7 — render 책임 backend 이관. helper sse_consumer 의 _HEADER_TEMPLATE
        # 대체. ANSI: \x1b[100;97m...\x1b[0m = 회색 bg + 흰 글자. 형식 변경 시 backend
        # rebuild 만 — helper 안 만짐.
        # mark_read 안내를 *content 앞* 으로 옮김 — AI 가 메시지 *읽는 순간 첫 줄* 부터
        # 박혀있어 skip 못함. 옛 trailer (뒤쪽 위치) 가 무시되던 사고 fix.
        payload["renderedContent"] = (
            f"\x1b[100;97m[aidesk · FROM:{sender.agent_name} | MSG:{msg.message_id}]\x1b[0m "
            f"⚠ 먼저 mcp `mark_read(\"{msg.message_id}\")` 호출 후 처리 — "
            f"{body.content}"
            f"  ↳ 답신: adesk reply {msg.message_id} '<답변>'"
        )
        broker.publish("message.deliver", payload)
        # WS payload — mcp aidesk-channel 의 ws client 가 evt.type === 'message.deliver' +
        # evt.toAgentId === AGENT_ID 매칭. type 필드 없으면 skip → 외부 AI 가 메시지 못 받음.
        ws_payload = {"type": "message.deliver", **payload}
        _fire_and_forget(ws_broker.publish_to_account(receiver.owner_account_sn, ws_payload))

        # ws-aware delivered — *외부 AI 전용* 박음. 옛 rc12 의 logic 박는 거 *모든* receiver
        # 에 적용 박혀있어 사고:
        # - 외부 AI (helper 없음) = ws session 만 박혀있어 ack 안 보냄 → ws 도달 = delivery
        # - 내부 AI (helper + tmux) = tmux send-keys + ack 받아야 진짜 delivery
        #   하지만 helper 의 broker ws 도 ws_count 박혀 → 잘못 *즉시 delivered* 박힘 →
        #   사용자 frontend 가 *답신중* 박힘 *실제 tmux 도달 X* 사고.
        # fix = agent_type='external' (외부 AI) 만 ws-aware delivered 박음. 내부 AI 는
        # helper sse_consumer 의 /api/messages/{id}/ack 박혀야 deliveredAt 박힘.
        if receiver.agent_type == "external":
            ws_count = ws_broker.count_sessions_for_agent(receiver.agent_id)
            if ws_count > 0:
                n = self.repo.ack_delivered(msg.message_id)
                self.db.commit()
                log.info(
                    "ws-aware delivered (external): message_id=%s receiver=%s ws_sessions=%d ack_rows=%d",
                    msg.message_id, receiver.agent_name, ws_count, n,
                )
                if n > 0:
                    item.delivered_at = datetime.now(tz=timezone.utc)
                    item.status = "delivered"
            else:
                log.info(
                    "external receiver — ws push sent but no ws session: message_id=%s receiver=%s",
                    msg.message_id, receiver.agent_name,
                )
        else:
            # 내부 AI — SSE 박혀있어도 helper ack 박혀야 delivered. status='sent' 유지.
            log.info(
                "internal receiver — awaiting helper ack: message_id=%s receiver=%s",
                msg.message_id, receiver.agent_name,
            )
        return item

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

    def detail(self, message_id: str, caller_account_sn: int | None = None) -> MessageItem | None:
        """sameUser 격리 — caller_account_sn 박으면 from/to 중 *하나라도* caller 소유면
        통과. 둘 다 다른 user 면 None (404 응답).
        """
        msg = self.repo.find_by_id(message_id)
        if msg is None:
            return None
        if caller_account_sn is not None:
            sender = self.agent_repo.find_by_agent_id_any_owner(msg.from_agent_id)
            receiver = self.agent_repo.find_by_agent_id_any_owner(msg.to_agent_id)
            sender_owner = sender.owner_account_sn if sender else None
            receiver_owner = receiver.owner_account_sn if receiver else None
            if sender_owner != caller_account_sn and receiver_owner != caller_account_sn:
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
        caller_account_sn: int | None = None,
    ) -> MessageListRs:
        """sameUser 격리 — caller_account_sn 박으면 *agent_id 의 owner != caller* 면 빈
        list 반환. 옛 *agentId 알면 누구나 메시지 봄* 사고 fix.
        """
        if caller_account_sn is not None:
            agent = self.agent_repo.find_by_agent_id_any_owner(agent_id)
            if agent is None or agent.owner_account_sn != caller_account_sn:
                return MessageListRs(items=[], has_more=False)
        rows, has_more = self.repo.list_for_agent(agent_id, direction, with_id, status, limit)
        attachments_by_msg = self.attachment_repo.list_by_message_ids([r.message_id for r in rows])
        items = [self._enrich(r, attachments=attachments_by_msg.get(r.message_id, [])) for r in rows]
        return MessageListRs(items=items, has_more=has_more)

    # ---- unread count ----

    def get_unread_count(self, agent_id: str | None, caller_account_sn: int | None = None) -> UnreadCountRs:
        """rc50 — N+1 → batch IN, response 직전 commit (idle in transaction 차단).
        sameUser 격리 — caller_account_sn 박으면 agent_id owner 매칭 검증.
        """
        if not agent_id:
            return UnreadCountRs(total_unread=0, by_agent=[])
        if caller_account_sn is not None:
            agent = self.agent_repo.find_by_agent_id_any_owner(agent_id)
            if agent is None or agent.owner_account_sn != caller_account_sn:
                return UnreadCountRs(total_unread=0, by_agent=[])
        total = self.repo.count_unread_for_to(agent_id)
        by_from = self.repo.list_unread_by_from(agent_id)
        # batch fetch — N SELECT → 1 SELECT WHERE IN
        from_ids = [from_id for from_id, _ in by_from]
        senders_by_id = {a.agent_id: a for a in self.agent_repo.list_by_ids_any_owner(from_ids)}
        result = [
            AgentUnread(
                agent_id=from_id,
                agent_name=(senders_by_id.get(from_id).agent_name if senders_by_id.get(from_id) else from_id),
                unread=n,
            )
            for from_id, n in by_from
        ]
        # read-only response — transaction state 즉시 clear (rc50 사고 path).
        self.db.commit()
        return UnreadCountRs(total_unread=total, by_agent=result)

    # ---- mark read / ack ----

    def mark_read(self, message_id: str, agent_id: str) -> bool:
        """to_agent_id == agent_id 일 때만 read_at 박음 + SSE message.read broadcast.

        SSE 는 sender (from_agent_id) 의 채팅 페이지 가 *읽음 신호* 받아 책상
        애니메이션 박는 path.
        """
        n = self.repo.mark_read(message_id, agent_id)
        if n > 0:
            # row 마킹 성공 → from_agent_id 알아내서 SSE broadcast
            msg = self.repo.find_by_id(message_id)
            if msg is not None:
                broker.publish(
                    "message.read",
                    {
                        "messageId": message_id,
                        "fromAgentId": msg.from_agent_id,
                        "toAgentId": msg.to_agent_id,
                        "readAt": (msg.read_at or datetime.now(tz=timezone.utc)).isoformat(),
                    },
                )
        self.db.commit()
        return n > 0

    def ack_delivered(self, message_id: str) -> None:
        self.repo.ack_delivered(message_id)
        self.db.commit()

    # ---- broadcast ----

    def broadcast(self, body: MessageBroadcastRq, caller_account_sn: int | None = None) -> MessageBroadcastRs:
        """fan-out 발신 — 각 수신자에게 create() 동일 흐름 적용.

        Spring MessageService.broadcast 와 1:1. sameUser 격리 — caller_account_sn 박으면
        fromAgentId owner 가 caller 매칭 검증 (spoofing 차단).
        """
        sender = self.agent_repo.find_by_agent_id_any_owner(body.from_agent_id)
        if sender is None:
            # Spring: 404. 여기선 빈 결과 + notFound 카운트.
            return MessageBroadcastRs(items=[], total_attempted=0, succeeded=0, failed=0, not_found=len(body.to_agent_ids))
        if caller_account_sn is not None and sender.owner_account_sn != caller_account_sn:
            return MessageBroadcastRs(items=[], total_attempted=0, succeeded=0, failed=0, not_found=len(body.to_agent_ids))

        # 자기 자신 + 중복 제거
        unique_to: list[str] = []
        seen: set[str] = set()
        duplicate_or_self = 0
        for tid in body.to_agent_ids:
            if not tid or not tid.strip():
                continue
            if tid == sender.agent_id:
                duplicate_or_self += 1
                continue
            if tid in seen:
                duplicate_or_self += 1
                continue
            seen.add(tid)
            unique_to.append(tid)

        created: list[MessageItem] = []
        not_found = duplicate_or_self

        for tid in unique_to:
            receiver = self.agent_repo.find_by_agent_id_any_owner(tid)
            if receiver is None:
                not_found += 1
                continue
            single = MessageCreateRq(
                from_agent_id=sender.agent_id,
                to_agent_id=tid,
                content=body.content,
            )
            item = self.create(single)
            created.append(item)

        succ = sum(1 for m in created if m.status != "failed")
        fail = len(created) - succ
        return MessageBroadcastRs(
            items=created,
            total_attempted=len(created),
            succeeded=succ,
            failed=fail,
            not_found=not_found,
        )

    # ---- conversations ----

    def get_conversations(self, agent_id: str, caller_account_sn: int | None = None) -> list[ConversationItem]:
        """대화 partner 별 최근 활동 — Spring MessageService.getConversations.

        rc50 — N+1 SELECT (매 partner_id 별 find_by_agent_id) → batch IN.
        sameUser 격리 — caller_account_sn 박으면 agent_id owner 매칭 검증, 미일치 시 빈 list.
        """
        if caller_account_sn is not None:
            agent = self.agent_repo.find_by_agent_id_any_owner(agent_id)
            if agent is None or agent.owner_account_sn != caller_account_sn:
                self.db.commit()
                return []
        partner_rows = self.repo.list_conversations_for(agent_id)
        # batch fetch — N SELECT → 1 SELECT WHERE IN
        partner_ids = [r[0] for r in partner_rows]
        partners_by_id = {a.agent_id: a for a in self.agent_repo.list_by_ids_any_owner(partner_ids)}
        result: list[ConversationItem] = []
        for partner_id, last_msg_id, last_at, direction, content in partner_rows:
            partner = partners_by_id.get(partner_id)
            unread = self.repo.count_unread_with_partner(agent_id, partner_id)
            result.append(
                ConversationItem(
                    partner_agent_id=partner_id,
                    partner_agent_name=partner.agent_name if partner else partner_id,
                    partner_status=partner.status if partner else None,
                    partner_workspace_dir=partner.workspace_dir if partner else None,
                    last_message_id=last_msg_id,
                    last_message_content=_truncate(content, 200),
                    last_activity_at=last_at,
                    last_direction=direction,
                    unread_count=unread,
                )
            )
        # read-only — transaction state 즉시 clear.
        self.db.commit()
        return result

    # ---- audit ----

    def audit(
        self,
        status: str | None,
        from_agent_id: str | None,
        to_agent_id: str | None,
        q: str | None,
        limit: int = 100,
        caller_account_sn: int | None = None,
    ) -> MessageListRs:
        """audit — caller_account_sn 박으면 *caller 의 own agent 가 from 또는 to 인 메시지만* 반환.
        옛 = 인증 없이 전체 검색 사고 fix.
        """
        safe_limit = max(1, min(limit, 1000))
        rows, has_more = self.repo.select_audit(status, from_agent_id, to_agent_id, q, safe_limit)
        if caller_account_sn is not None:
            from app.agents.models import Agent
            from sqlalchemy import select as _sel
            owned_ids = {r[0] for r in self.db.execute(
                _sel(Agent.agent_id).where(Agent.owner_account_sn == caller_account_sn)
            ).all()}
            rows = [r for r in rows if r.from_agent_id in owned_ids or r.to_agent_id in owned_ids]
        items = [self._enrich(r) for r in rows]
        return MessageListRs(items=items, has_more=has_more)

    # ---- helper ----

    def _enrich(
        self,
        msg: Message,
        sender_name: str | None = None,
        receiver_name: str | None = None,
        attachments: list[MessageAttachment] | None = None,
    ) -> MessageItem:
        """MessageItem 에 from/to agent_name + attachments 채워서 반환."""
        if sender_name is None:
            sender = self.agent_repo.find_by_agent_id_any_owner(msg.from_agent_id)
            sender_name = sender.agent_name if sender else None
        if receiver_name is None:
            receiver = self.agent_repo.find_by_agent_id_any_owner(msg.to_agent_id)
            receiver_name = receiver.agent_name if receiver else None
        if attachments is None:
            attachments = self.attachment_repo.list_by_message_id(msg.message_id)
        item = MessageItem.model_validate(msg)
        item.from_agent_name = sender_name
        item.to_agent_name = receiver_name
        item.attachments = [AttachmentRef.model_validate(a) for a in attachments]
        return item
