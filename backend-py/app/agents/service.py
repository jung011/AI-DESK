"""agents business logic — Spring AgentService 일부 (sameUser only).

cross-user / channel-aware canCommunicate 는 messages 도메인 포팅 turn 에 합쳐 완성.
realtime 도 messages 의 partners 의존 → 현재는 partners=[] stub.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.models import AiAgent
from app.agents.repository import AgentRepository
from app.agents.schemas import AgentCreateRq, AgentItem, AgentListRs, AgentRealtimeItem

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

    def get_list(self, owner_account_sn: int, status: str | None = None) -> AgentListRs:
        """dashboard cookie 인증 호출 — sameUser 안 agent. status 필터 optional.

        TODO (messages turn): mcp callerAgentId 동봉 시 channel-aware canCommunicate
        로 cross-user 필터링.
        """
        rows = self.repo.list_by_owner(owner_account_sn, status)
        items = [_to_item(r) for r in rows]
        return AgentListRs(items=items)

    def get_realtime(self) -> list[AgentRealtimeItem]:
        """외부 시각화 BE 가 소비하는 5필드 응답.

        partners 는 messages 도메인의 최근 대화 partner 추적 필요 → 현재 stub (빈 list).
        """
        rows = self.repo.list_all_active()
        result: list[AgentRealtimeItem] = []
        for r in rows:
            state = _map_status_to_state(r.status)
            result.append(
                AgentRealtimeItem(
                    agent_id=r.agent_id,
                    name=r.agent_name,
                    state=state,
                    partners=[],  # TODO(messages-port)
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
        return _to_item(agent)

    def delete(self, agent_id: str) -> bool:
        """soft delete. helper 의 tmux/.claude history 정리는 frontend 가 별도 호출."""
        n = self.repo.soft_delete(agent_id)
        self.db.commit()
        return n > 0

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
