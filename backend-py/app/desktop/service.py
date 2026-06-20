"""desktop business logic — Spring DesktopService.applyLocalInfo 와 1:1.

helper 의 30초 reporter payload 처리:
- workspaces[].workspace_dir 으로 agent 매칭
- tmux fact-check (보고된 session list 안 없으면 offline 강제)
- compacting stick (helper 의 'active' override 차단)
- status 변화 없어도 updated_at touch (colleague online window 위해)
"""
import logging

from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.desktop.schemas import DesktopLocalInfoRq, DesktopLocalInfoRs

log = logging.getLogger(__name__)


class DesktopService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AgentRepository(db)

    def apply_local_info(self, req: DesktopLocalInfoRq) -> DesktopLocalInfoRs:
        rs = DesktopLocalInfoRs(total_workspaces=len(req.workspaces))
        if not req.workspaces:
            return rs

        # 모든 user 의 agent — helper-user binding 후속 작업 전까지 매칭만.
        # 외부 AI (agent_type='external') 는 by_ws 에서 제외 — workspace_dir 가 placeholder
        # '(external)' 라 매칭 가능성 X 지만 *명시적 safeguard*. helper reporter 의 어떤
        # path 라도 외부 AI 강등 시도 안 함 (rc22 fix). [[fastapi-watcher-external-skip]]
        # 패턴 정합.
        all_agents = self.repo.list_all_active()
        by_ws = {
            a.workspace_dir: a
            for a in all_agents
            if a.workspace_dir and a.agent_type != "external"
        }

        # 보고된 tmux session 이름 set — agent.tmux_session 이 여기 없으면 offline 강제
        reported_tmux = {t.name for t in req.tmux_sessions if t.name}

        matched = 0
        updated = 0
        for w in req.workspaces:
            if not w.workspace_dir or not w.status:
                continue
            agent = by_ws.get(w.workspace_dir)
            if agent is None:
                continue
            matched += 1

            # tmux fact-check
            effective_status = w.status
            if agent.tmux_session and agent.tmux_session not in reported_tmux:
                effective_status = "offline"

            # compacting stick — helper reporter 의 status override 차단
            if agent.status == "compacting":
                self.repo.touch_updated_at(agent.agent_id)
                continue

            if effective_status != agent.status:
                self.repo.update_status_from_watcher(agent.agent_id, effective_status)
                updated += 1
                log.debug(
                    "desktop: agent=%s status %s -> %s",
                    agent.agent_name, agent.status, effective_status,
                )
            else:
                # 변화 없어도 helper 살아있다는 신호 — colleague online window 용
                self.repo.touch_updated_at(agent.agent_id)

        self.db.commit()
        rs.matched_agents = matched
        rs.updated_agents = updated
        return rs
