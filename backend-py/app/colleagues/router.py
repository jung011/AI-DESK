"""colleagues router — /api/colleagues."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.auth.schemas import AuthenticatedUser
from app.colleagues.schemas import ColleagueListRs
from app.colleagues.service import ColleagueService
from app.common.response import ApiEnvelope, ok
from app.core.database import get_db

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "colleagues", "status": "ok"}


@router.get("", response_model=ApiEnvelope[ColleagueListRs])
async def list_colleagues(
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[ColleagueListRs]:
    svc = ColleagueService(db)
    return ok(svc.get_list(user.account_sn))
