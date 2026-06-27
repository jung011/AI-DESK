"""agents DB 접근 — Spring AgentMapper 와 1:1."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agents.models import AiAgent

log = logging.getLogger(__name__)


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

    def find_human_for_account(self, account_sn: int) -> AiAgent | None:
        """휴먼 entity (model='human') row 조회 — owner_account_sn 매칭. task push 시
        from_agent_id 로 사용. [[project-user-entity-model]] + [[feedback-human-sender-policy-exempt]]."""
        return self.db.execute(
            select(AiAgent).where(
                AiAgent.owner_account_sn == account_sn,
                AiAgent.model == "human",
                AiAgent.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    def list_by_ids_any_owner(self, agent_ids: list[str]) -> list[AiAgent]:
        """rc50 — N+1 SELECT 회피용 batch fetch. 빈 list 면 empty return.

        get_conversations / get_unread_count 같은 list response 가 매 row 별
        find_by_agent_id 호출하면 idle in transaction 누적 + pool 고갈 위험.
        WHERE agent_id IN (...) 1 query 로 모든 partner / sender 일괄 조회.
        """
        if not agent_ids:
            return []
        return list(
            self.db.execute(
                select(AiAgent).where(AiAgent.agent_id.in_(agent_ids))
            ).scalars()
        )

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

    def _is_external_agent(self, agent_id: str) -> bool:
        """rc24 — 외부 AI 의 status='offline' 차단용 helper."""
        row = self.db.execute(
            select(AiAgent.agent_type).where(AiAgent.agent_id == agent_id)
        ).first()
        return bool(row and row[0] == "external")

    def update_status(self, agent_id: str, status: str | None) -> int:
        """status 갱신. Spring updateStatus — context_pct 는 statusline 이 별도로 기록.

        rc24 — 외부 AI 의 'offline' 마킹 차단. mcp ws 가 유일한 status source.
        staging shared DB 같은 잔재 사고 ([[feedback-staging-shared-db-hazard]]) 대비
        defense-in-depth.
        """
        if status == "offline" and self._is_external_agent(agent_id):
            log.warning("update_status 'offline' BLOCKED for external agent_id=%s", agent_id)
            return 0
        result = self.db.execute(
            update(AiAgent)
            .where(AiAgent.agent_id == agent_id, AiAgent.deleted_at.is_(None))
            .values(status=status)
        )
        return result.rowcount

    def update_context_pct(self, agent_id: str, context_pct: int) -> int:
        """statusline / helper reporter 가 호출 — agent 별 context 사용률 갱신."""
        result = self.db.execute(
            update(AiAgent)
            .where(AiAgent.agent_id == agent_id, AiAgent.deleted_at.is_(None))
            .values(context_pct=context_pct)
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
        """desktop reporter / scheduler 가 status 갱신. updated_at 도 갱신.

        rc24 — 외부 AI 의 'offline' 마킹 차단. mcp ws 가 외부 AI 의 유일한 status source.
        ws connect 시 'idle' 마킹만 통과. staging shared DB 같은 잔재 사고 대비 defense-in-depth.
        """
        if status == "offline" and self._is_external_agent(agent_id):
            log.warning("update_status_from_watcher 'offline' BLOCKED for external agent_id=%s", agent_id)
            return 0
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

    def list_stale_idle_for_offline(self, threshold_seconds: int) -> list[AiAgent]:
        """좀비 idle agent — *helper 죽었지만* status='idle' 영구 잔류 케이스 청산.

        D 일원화 (comm-architecture-improvement.md 의 idle→offline 전이 누락 fix):
        - 현재 watcher 는 active → idle 강등만 함.
        - helper 가 죽으면 *idle 영구* — heartbeat 안 와도 idle 잔류.
        - 추가 threshold (default 5분) 안 갱신 없으면 *진짜 offline* 마킹.

        외부 AI 제외 — ws session 이 유일한 status source.
        human 제외 — helper 안 돌리니 갱신 없음 (영구 idle 정상).
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=threshold_seconds)
        stmt = select(AiAgent).where(
            AiAgent.deleted_at.is_(None),
            AiAgent.status == "idle",
            AiAgent.updated_at < cutoff,
            AiAgent.agent_type != "external",
            AiAgent.agent_type != "human",
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
