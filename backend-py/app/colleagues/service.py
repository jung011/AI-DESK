"""colleagues — 사내 동료 디렉토리. Spring ColleagueService 와 1:1.

본인 외 user 의 (me) AI + 본인의 external AI 통합 list.
online = (me) agent.updated_at 이 5분 이내.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import AiAgent
from app.auth.models import User
from app.colleagues.schemas import ColleagueItem, ColleagueListRs

ONLINE_WINDOW = timedelta(minutes=5)


class ColleagueService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_list(self, me_account_sn: int) -> ColleagueListRs:
        now = datetime.now(timezone.utc)
        rows: list[ColleagueItem] = []

        # 1) 본인 외 user 의 (me) AI — tmux_session LIKE 'aidesk-self-%'
        stmt = (
            select(User, AiAgent)
            .join(AiAgent, AiAgent.owner_account_sn == User.account_sn)
            .where(
                User.account_sn != me_account_sn,
                AiAgent.tmux_session.like("aidesk-self-%"),
                AiAgent.deleted_at.is_(None),
            )
        )
        for user, agent in self.db.execute(stmt).all():
            rows.append(self._to_item(user, agent, now))

        # 2) 본인의 external AI
        stmt2 = (
            select(User, AiAgent)
            .join(AiAgent, AiAgent.owner_account_sn == User.account_sn)
            .where(
                User.account_sn == me_account_sn,
                AiAgent.agent_type == "external",
                AiAgent.deleted_at.is_(None),
            )
        )
        for user, agent in self.db.execute(stmt2).all():
            rows.append(self._to_item(user, agent, now))

        return ColleagueListRs(items=rows)

    @staticmethod
    def _to_item(user: User, agent: AiAgent, now: datetime) -> ColleagueItem:
        online = False
        if agent.updated_at is not None:
            # SQLAlchemy 가 server_default=func.now() 로 박을 때 tz-naive 일 수 있어 보정.
            ts = agent.updated_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            online = (now - ts) <= ONLINE_WINDOW
        return ColleagueItem(
            account_sn=user.account_sn,
            login_id=user.login_id,
            display_name=user.display_name,
            me_agent_id=agent.agent_id,
            me_agent_name=agent.agent_name,
            me_status=agent.status,
            me_context_pct=agent.context_pct,
            me_workspace_dir=agent.workspace_dir,
            me_updated_at=agent.updated_at,
            online=online,
            agent_type=agent.agent_type,
        )
