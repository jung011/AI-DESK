"""external agent business logic — Spring ExternalAgentService 와 1:1.

- raw token 은 secrets.token_urlsafe(32) — URL-safe base64
- DB 에는 sha256(raw).hexdigest() 만. 원본은 발급 직후 1회 응답만.
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.external.schemas import ExternalAgentCreateRq, ExternalAgentTokenRs
from app.agents.models import AiAgent
from app.agents.repository import AgentRepository
from app.core.exceptions import ApiException
from app.messages.sse import broker

log = logging.getLogger(__name__)

EXTERNAL_MODEL_PLACEHOLDER = "external"
EXTERNAL_WORKSPACE_PLACEHOLDER = "(external)"


def _generate_raw_token() -> str:
    """URL-safe Bearer token — Spring BearerTokenUtil.generateRawToken 과 동등 entropy.

    Spring 정합 — `aidesk_ext_` prefix 박음 (옛 마이그 시 누락된 regression fix, rc17).
    ws.py 의 prefix check 는 rc11 부터 제거됨 (backward compat — 옛 prefix 없는 token 도 허용).
    """
    return "aidesk_ext_" + secrets.token_urlsafe(32)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ExternalAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AgentRepository(db)

    def create(self, body: ExternalAgentCreateRq, owner_account_sn: int) -> ExternalAgentTokenRs:
        agent_id = str(uuid.uuid4())
        raw = _generate_raw_token()
        agent = AiAgent(
            agent_id=agent_id,
            agent_name=body.agent_name.strip(),
            owner_account_sn=owner_account_sn,
            workspace_dir=EXTERNAL_WORKSPACE_PLACEHOLDER,
            tmux_session=f"external-{agent_id}",
            status="offline",
            model=EXTERNAL_MODEL_PLACEHOLDER,
            agent_type="external",
            bearer_token_hash=_hash_token(raw),
            bearer_token_created_at=datetime.now(tz=timezone.utc),
        )
        self.repo.insert(agent)
        self.db.commit()
        log.info("external-agent created agentId=%s name=%s owner=%s", agent_id, body.agent_name, owner_account_sn)
        broker.publish("agent.changed", {"event": "external.created", "agentId": agent_id})
        return ExternalAgentTokenRs(agent_id=agent_id, agent_name=agent.agent_name, token=raw)

    def rotate_token(self, agent_id: str, owner_account_sn: int) -> ExternalAgentTokenRs:
        agent = self._find_owned_external(agent_id, owner_account_sn)
        raw = _generate_raw_token()
        agent.bearer_token_hash = _hash_token(raw)
        agent.bearer_token_created_at = datetime.now(tz=timezone.utc)
        self.db.commit()
        log.info("external-agent token rotated agentId=%s", agent_id)
        broker.publish("agent.changed", {"event": "external.rotated", "agentId": agent_id})
        return ExternalAgentTokenRs(agent_id=agent_id, agent_name=agent.agent_name, token=raw)

    def revoke_token(self, agent_id: str, owner_account_sn: int) -> None:
        agent = self._find_owned_external(agent_id, owner_account_sn)
        agent.bearer_token_hash = None
        agent.bearer_token_created_at = None
        # ws closeForAgent (external-ai-lifecycle-safeguards) — bot adapter 도 401 받아 종료.
        # 별도 ws layer 가 없을 시점 (PoC) 이라 row 의 hash 만 무효화.
        self.db.commit()
        log.info("external-agent token revoked agentId=%s", agent_id)
        broker.publish("agent.changed", {"event": "external.revoked", "agentId": agent_id})

    def _find_owned_external(self, agent_id: str, owner_account_sn: int) -> AiAgent:
        agent = self.repo.find_by_agent_id(agent_id)
        if agent is None or agent.agent_type != "external" or agent.owner_account_sn != owner_account_sn:
            raise ApiException(404, "external agent not found", http_status=404)
        return agent
