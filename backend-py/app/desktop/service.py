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
from app.messages.sse import broker

log = logging.getLogger(__name__)

# in-memory cache — last reported prompt_dialog state per agent_id.
# K8s replica > 1 시 inconsistent (옛 broker 와 같은 한계). 변화 감지 + 중복 publish 차단용.
_last_prompt_dialog: dict[str, dict | None] = {}


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
        # claudeAlive=False 인 session — 사용자가 claude 종료한 case. 옛 path 는 zsh prompt
        # 만 살아남은 tmux session 을 idle 그대로 → 'offline' 강제 (helper 0.8.57+).
        # helper 옛 버전 (claudeAlive 미보고) 호환 — None 이면 그대로 통과.
        dead_claude_tmux = {t.name for t in req.tmux_sessions if t.name and t.claude_alive is False}
        # helper 0.8.69+ — prompt dialog per tmux session. agent 매칭 후 변화 감지 publish.
        prompt_by_tmux = {t.name: t.prompt_dialog for t in req.tmux_sessions if t.name}

        matched = 0
        updated = 0
        matched_ids: list[str] = []
        for w in req.workspaces:
            if not w.workspace_dir or not w.status:
                continue
            agent = by_ws.get(w.workspace_dir)
            if agent is None:
                continue
            matched += 1
            matched_ids.append(agent.agent_id)

            # tmux fact-check
            effective_status = w.status
            if agent.tmux_session and agent.tmux_session not in reported_tmux:
                effective_status = "offline"
            # claude detect — tmux 살아있어도 pane tree 에 claude 없으면 offline.
            elif agent.tmux_session and agent.tmux_session in dead_claude_tmux:
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

            # context_pct — workspace 별 별도. helper 가 aidesk-usage/{sessionId}.json
            # 의 cwd 매칭으로 추출. None 이면 갱신 skip.
            if w.context_pct is not None:
                self.repo.update_context_pct(agent.agent_id, w.context_pct)

            # prompt_dialog change detection — variation 감지 시 SSE publish.
            # in-memory cache 기반 — replica > 1 시 inconsistent 하지만 옛 broker 와 동일 한계.
            current_pd = prompt_by_tmux.get(agent.tmux_session) if agent.tmux_session else None
            last_pd = _last_prompt_dialog.get(agent.agent_id)
            if current_pd != last_pd:
                _last_prompt_dialog[agent.agent_id] = current_pd
                broker.publish(
                    "agent.prompt-dialog",
                    {
                        "agentId": agent.agent_id,
                        "tmuxSession": agent.tmux_session,
                        "options": (current_pd or {}).get("options") if current_pd else None,
                    },
                )
                log.info(
                    "desktop: agent=%s prompt_dialog change %s -> %s",
                    agent.agent_name,
                    "present" if last_pd else "none",
                    "present" if current_pd else "none",
                )

        self.db.commit()
        rs.matched_agents = matched
        rs.updated_agents = updated
        rs.matched_agent_ids = matched_ids
        return rs
