"""agents DB 접근 — Spring AgentMapper 와 1:1."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agents.models import AiAgent


class AgentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- read ----

    def list_by_owner(self, owner_account_sn: int, status: str | None = None) -> list[AiAgent]:
        """Spring selectList(meAccountSn, status) — sameUser 필터, deleted 제외."""
        stmt = select(AiAgent).where(
            AiAgent.owner_account_sn == owner_account_sn,
            AiAgent.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(AiAgent.status == status)
        return list(self.db.execute(stmt).scalars())

    def list_all_active(self) -> list[AiAgent]:
        """Spring selectAllForSystem — deleted 제외 전체. 권한 필터는 caller 가 처리."""
        return list(
            self.db.execute(select(AiAgent).where(AiAgent.deleted_at.is_(None))).scalars()
        )

    def find_by_agent_id(self, agent_id: str) -> AiAgent | None:
        """deleted 제외 — 정상 조회."""
        return self.db.execute(
            select(AiAgent).where(
                AiAgent.agent_id == agent_id,
                AiAgent.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    def find_by_agent_id_any_owner(self, agent_id: str) -> AiAgent | None:
        """Spring selectByIdAnyOwner — caller 인증 시 owner 검증 전 lookup."""
        return self.db.execute(select(AiAgent).where(AiAgent.agent_id == agent_id)).scalar_one_or_none()

    def find_by_tmux_session(self, tmux_session: str) -> AiAgent | None:
        return self.db.execute(
            select(AiAgent).where(
                AiAgent.tmux_session == tmux_session,
                AiAgent.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    # ---- write ----

    def insert(self, agent: AiAgent) -> AiAgent:
        self.db.add(agent)
        self.db.flush()
        return agent

    def update_status(self, agent_id: str, status: str | None) -> int:
        """status 갱신. Spring updateStatus — context_pct 는 statusline 이 별도로 기록."""
        result = self.db.execute(
            update(AiAgent)
            .where(AiAgent.agent_id == agent_id, AiAgent.deleted_at.is_(None))
            .values(status=status)
        )
        return result.rowcount

    def update_workspace_dir(self, agent_id: str, workspace_dir: str, owner_account_sn: int) -> int:
        result = self.db.execute(
            update(AiAgent)
            .where(
                AiAgent.agent_id == agent_id,
                AiAgent.owner_account_sn == owner_account_sn,
                AiAgent.deleted_at.is_(None),
            )
            .values(workspace_dir=workspace_dir)
        )
        return result.rowcount

    def update_status_from_watcher(self, agent_id: str, status: str) -> int:
        """desktop reporter / scheduler 가 status 갱신. updated_at 도 갱신."""
        result = self.db.execute(
            update(AiAgent)
            .where(AiAgent.agent_id == agent_id, AiAgent.deleted_at.is_(None))
            .values(status=status, updated_at=datetime.now(tz=timezone.utc))
        )
        return result.rowcount

    def touch_updated_at(self, agent_id: str) -> int:
        """status 변화 없어도 helper 가 살아있다는 신호로 updated_at 만 갱신.

        ColleagueService 의 online window 판정이 updated_at 만 봄.
        """
        result = self.db.execute(
            update(AiAgent)
            .where(AiAgent.agent_id == agent_id, AiAgent.deleted_at.is_(None))
            .values(updated_at=datetime.now(tz=timezone.utc))
        )
        return result.rowcount

    def list_stale_active(self, threshold_seconds: int) -> list[AiAgent]:
        """updated_at 이 threshold 이전 + status 가 'active' 인 agent — active → idle 강등 대상.

        rc19 design 정정 — idle ≠ offline:
        - idle = 살아있는 상태 (prompt 대기 중). 90초 stale 라도 idle 유지.
        - active → idle 강등 만 (생존 신호 끊김, 그러나 살아있다 가정).
        - offline = 진짜 종료 (helper reporter 의 tmux 없음 보고 또는 agent delete) 만 마킹.

        외부 AI 도 제외 (helper 없음 + ws session 만이 status source).
        Spring 정합 — 옛 Spring 의 watcher 도 offline 마킹 안 함.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=threshold_seconds)
        stmt = select(AiAgent).where(
            AiAgent.deleted_at.is_(None),
            AiAgent.status == "active",  # idle 제외 — idle = 살아있는 상태
            AiAgent.updated_at < cutoff,
            AiAgent.agent_type != "external",
        )
        return list(self.db.execute(stmt).scalars())

    def soft_delete(self, agent_id: str) -> int:
        """deleted_at 마킹 — hard delete X (audit 보존)."""
        result = self.db.execute(
            update(AiAgent)
            .where(AiAgent.agent_id == agent_id, AiAgent.deleted_at.is_(None))
            .values(deleted_at=datetime.now(tz=timezone.utc))
        )
        return result.rowcount
