"""external agents router — /api/agents/external/*."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.external.schemas import ExternalAgentCreateRq, ExternalAgentTokenRs
from app.agents.external.service import ExternalAgentService
from app.auth.deps import current_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, ok
from app.core.database import get_db

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "agents/external", "status": "ok"}


@router.post("", response_model=ApiEnvelope[ExternalAgentTokenRs])
async def create(
    body: ExternalAgentCreateRq,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[ExternalAgentTokenRs]:
    svc = ExternalAgentService(db)
    return ok(svc.create(body, user.account_sn))


@router.post("/{agent_id}/token", response_model=ApiEnvelope[ExternalAgentTokenRs])
async def rotate_token(
    agent_id: str,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[ExternalAgentTokenRs]:
    svc = ExternalAgentService(db)
    return ok(svc.rotate_token(agent_id, user.account_sn))


@router.delete("/{agent_id}/token", response_model=ApiEnvelope[None])
async def revoke_token(
    agent_id: str,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[None]:
    svc = ExternalAgentService(db)
    svc.revoke_token(agent_id, user.account_sn)
    return ok(None)
