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
    """agent 의 통신 channel — BOTH / A / B.

    Spring MessageService.channelOf 와 1:1.
    - BOTH : (me) 또는 휴먼 — 두 채널의 브릿지
    - A    : internal AI (helper 환경 worker)
    - B    : external AI (mcp service, 사내 동료 채널)
    """
    if (agent.model or "").lower() == "human":
        return "BOTH"
    ts = agent.tmux_session or ""
    if ts.startswith("aidesk-self-"):
        return "BOTH"
    if (agent.agent_type or "").lower() == "external":
        return "B"
    return "A"


def can_communicate(caller: AiAgent, peer: AiAgent) -> bool:
    """두 agent 간 통신 허용 여부 — Spring canCommunicate 와 1:1.

    핵심:
    - self → self: 차단
    - BOTH↔BOTH: cross-user 허용 (사내 동료 채널 브릿지 간 통신)
    - BOTH↔A/B: sameUser 만 (internal/external 은 본인 user 의 사유 worker/service)
    - A/A: sameUser 만
    - B/B: sameUser 만 — 외부 AI 는 등록 user 격리
    - A↔B: 차단 — internal/external 직접 통신은 (me) 브릿지 경유
    """
    if caller is None or peer is None:
        return False
    if caller.agent_id == peer.agent_id:
        return False
    same_user = (
        caller.owner_account_sn is not None
        and caller.owner_account_sn == peer.owner_account_sn
    )
    from_ch = channel_of(caller)
    to_ch = channel_of(peer)
    if from_ch == "BOTH" and to_ch == "BOTH":
        return True
    if "BOTH" in (from_ch, to_ch):
        return same_user
    if from_ch != to_ch:
        return False
    return same_user


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
