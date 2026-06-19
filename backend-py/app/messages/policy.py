"""메시지 정책 — Spring MessagePolicyChecker 와 1:1.

규칙 (messages_backend.md):
- context guard : 수신 AI contextPct >= settings.message_context_limit_pct → 거절
- hop limit     : parent 의 hop_count + 1 > settings.message_hop_limit → 거절
- rate limit    : 발신 AI 분당 send 수 >= 한도 → 거절
- 1000자 limit  : schemas 의 max_length 로 처리 (여기선 X)
- sameUser / channel-aware canCommunicate : 같은 user 안 + 본인/외부 channel 조합 허용
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.models import AiAgent
from app.core.config import get_settings
from app.messages.models import Message
from app.messages.repository import MessageRepository

settings = get_settings()


@dataclass(frozen=True)
class PolicyResult:
    accepted: bool
    reason: str = ""

    @classmethod
    def accept(cls) -> PolicyResult:
        return cls(accepted=True)

    @classmethod
    def reject(cls, reason: str) -> PolicyResult:
        return cls(accepted=False, reason=reason)


def channel_of(agent: AiAgent) -> str:
    """agent 의 통신 channel — internal / external / bridge (me 또는 human).

    sameUser 안 internal AI 들끼리만 통신 가능. external 은 cross-user 가능. (me)/human 은
    bridge 라 양쪽 모두 닿을 수 있음.
    """
    t = (agent.agent_type or "internal").lower()
    if t in ("me", "human"):
        return "bridge"
    if t == "external":
        return "external"
    return "internal"


def can_communicate(caller: AiAgent, peer: AiAgent) -> bool:
    """caller 가 peer 에게 통신 가능한지.

    Spring MessageService.canCommunicate(caller, peer, callerCh, peerCh) 의 본질.
    핵심 규칙:
    - 같은 user (sameUser) 항상 허용
    - bridge (me / human) 양쪽 모두 닿음
    - 다른 user → external ↔ external / external ↔ bridge 허용. internal ↔ internal 차단
    """
    if caller.owner_account_sn == peer.owner_account_sn:
        return True
    caller_ch = channel_of(caller)
    peer_ch = channel_of(peer)
    if "bridge" in (caller_ch, peer_ch):
        return True
    if caller_ch == "external" and peer_ch == "external":
        return True
    return False


def check_send(
    sender: AiAgent,
    receiver: AiAgent,
    parent: Message | None,
    repo: MessageRepository,
) -> PolicyResult:
    """send 요청에 대한 정책 검사 — 거절 사유 1개 반환.

    1000자 limit 은 schemas.MessageCreateRq.content max_length 에서 차단.
    self-message 는 caller 가 별도로 처리.
    """
    # context guard
    if receiver.context_pct is not None and receiver.context_pct >= settings.message_context_limit_pct:
        return PolicyResult.reject(f"수신 AI 컨텍스트 {settings.message_context_limit_pct}% 초과")

    # hop limit
    if parent is not None:
        parent_hop = parent.hop_count or 0
        if parent_hop + 1 > settings.message_hop_limit:
            return PolicyResult.reject(f"위임 깊이 초과 (max {settings.message_hop_limit})")

    # rate limit — 분당 발신 수
    rate_limit = 30  # Spring 기본 (env 외부화 가능)
    recent = repo.count_recent_from(sender.agent_id, seconds=60)
    if recent >= rate_limit:
        return PolicyResult.reject(f"발신 한도 초과 (분당 {rate_limit}건)")

    # canCommunicate
    if not can_communicate(sender, receiver):
        return PolicyResult.reject("통신 권한 없음 (cross-user / channel mismatch)")

    return PolicyResult.accept()
