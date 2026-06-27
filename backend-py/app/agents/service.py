"""agents business logic — Spring AgentService 1:1 (channel-aware filter + realtime partners 포함)."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.models import AiAgent
from app.agents.repository import AgentRepository
from app.agents.schemas import AgentCreateRq, AgentItem, AgentListRs, AgentRealtimeItem
from app.messages.policy import can_communicate
from app.messages.repository import MessageRepository
from app.messages.sse import broker

log = logging.getLogger(__name__)

# Spring AgentService.MODEL_FULLNAMES
MODEL_FULLNAMES = {
    "claude": "claude-opus-4-7",
    "codex": "codex",
    "hermes": "hermes",
}


def _resolve_type(agent: AiAgent) -> str | None:
    """t_ai_agent.agent_type 컬럼 우선. 없으면 tmux_session 으로 derive."""
    if agent.agent_type:
        return agent.agent_type
    if agent.tmux_session.startswith("__human__:"):
        return "human"
    if agent.tmux_session.startswith("aidesk-self-"):
        return "me"
    return "internal"


def _to_item(agent: AiAgent) -> AgentItem:
    item = AgentItem.model_validate(agent)
    item.type = _resolve_type(agent)
    return item


class AgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AgentRepository(db)

    # ---- list / detail ----

    def get_list(
        self,
        owner_account_sn: int | None,
        status: str | None = None,
        caller_agent_id: str | None = None,
    ) -> AgentListRs:
        """Spring AgentService.getList(status, callerAgentId) 1:1.

        Mode:
        1) dashboard cookie 인증 호출 (caller_agent_id=None) — sameUser 안 agent
        2) mcp 의 list_agents (caller_agent_id 주어짐) — caller 의 channel 기준 권한 filter
        3) 비인증 + caller 모름 — *빈 list*. 옛 path 는 list_all_active 였지만 frontend
           cookie 인증 race 시점에도 같이 발화해서 sameUser 격리 위반 사고 (다른 user 의
           agent 잠시 노출). 정상 path 면 frontend 가 middleware redirect, mcp 는
           callerAgentId 박음. 빈 list 가 안전 default.
        """
        caller: AiAgent | None = None
        me = owner_account_sn
        if caller_agent_id:
            caller = self.repo.find_by_agent_id_any_owner(caller_agent_id)
            if me is None and caller is not None:
                me = caller.owner_account_sn

        if me is None:
            # 비인증 + caller 모름 — 보안 default (옛 list_all_active 폐기, sameUser 격리 위반 차단)
            return AgentListRs(items=[])
        if caller is not None:
            # channel-aware filter — canCommunicate 통과한 agent 만
            all_rows = self.repo.list_all_active()
            rows = [a for a in all_rows if can_communicate(caller, a)]
        else:
            rows = self.repo.list_by_owner(me, status)

        items = [_to_item(r) for r in rows]
        return AgentListRs(items=items)

    def get_realtime(self) -> list[AgentRealtimeItem]:
        """외부 시각화 BE 가 소비하는 5필드 응답. partners 는 최근 대화 partner agent_id."""
        msg_repo = MessageRepository(self.db)
        rows = self.repo.list_all_active()
        result: list[AgentRealtimeItem] = []
        for r in rows:
            state = _map_status_to_state(r.status)
            partners = msg_repo.list_recent_partners(r.agent_id, max_partners=10)
            result.append(
                AgentRealtimeItem(
                    agent_id=r.agent_id,
                    name=r.agent_name,
                    state=state,
                    partners=partners,
                    last_seen_at=r.updated_at,
                )
            )
        return result

    def detail(self, agent_id: str) -> AgentItem | None:
        agent = self.repo.find_by_agent_id(agent_id)
        return _to_item(agent) if agent else None

    # ---- create / delete ----

    def create(self, owner_account_sn: int, body: AgentCreateRq) -> AgentItem | None:
        """신규 internal AI 생성. agent_id = uuid, model 은 alias 풀이."""
        model = MODEL_FULLNAMES.get(body.model.lower(), body.model)
        agent = AiAgent(
            agent_id=str(uuid.uuid4()),
            agent_name=body.agent_name,
            owner_account_sn=owner_account_sn,
            workspace_dir=body.workspace_dir,
            tmux_session=f"aidesk-{uuid.uuid4().hex[:8]}",
            status="idle",
            model=model,
            agent_type="internal",
            started_at=datetime.now(timezone.utc),
        )
        self.repo.insert(agent)
        self.db.commit()
        self.db.refresh(agent)
        broker.publish("agent.changed", {"event": "internal.created", "agentId": agent.agent_id})
        return _to_item(agent)

    def delete(self, agent_id: str) -> bool:
        """soft delete. helper 의 tmux/.claude history 정리는 frontend 가 별도 호출."""
        n = self.repo.soft_delete(agent_id)
        self.db.commit()
        ok = n > 0
        if ok:
            broker.publish("agent.changed", {"event": "deleted", "agentId": agent_id})
        return ok

    # ---- status ----

    def update_status(self, agent_id: str, status: str | None) -> bool:
        """hook 이 호출 — compacting/idle/active 등 free-form string 그대로 저장.

        Spring DesktopService 의 compacting stick 정책은 desktop 도메인 turn 에.
        """
        if not status:
            return False
        n = self.repo.update_status(agent_id, status)
        self.db.commit()
        return n > 0


# ---- helpers ----

def _map_status_to_state(status: str) -> str:
    """t_ai_agent.status → 메타버스 시각화 state 매핑."""
    if status == "active":
        return "working"
    if status == "idle":
        return "idle"
    if status == "compacting":
        return "working"
    if status == "offline":
        return "offline"
    return status or "idle"
