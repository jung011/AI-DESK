"""settings router — /api/settings/*. Spring SettingController 와 1:1.

- GET  /a2a-workspace
- PUT  /a2a-workspace
- GET  /code-server
- GET  /workrole-file
- PUT  /workrole-file
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, fail, ok
from app.core.config import get_settings
from app.core.database import get_db
from app.settings.schemas import (
    A2aWorkspaceRq,
    A2aWorkspaceRs,
    CodeServerRs,
    WorkroleFileRq,
    WorkroleFileRs,
)
from app.settings.service import SettingService

router = APIRouter()
settings_env = get_settings()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "settings", "status": "ok"}


@router.get("/a2a-workspace", response_model=ApiEnvelope[A2aWorkspaceRs])
async def get_a2a_workspace(
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[A2aWorkspaceRs]:
    svc = SettingService(db)
    return ok(A2aWorkspaceRs(path=svc.get_a2a_workspace(user.account_sn)))


@router.put("/a2a-workspace", response_model=ApiEnvelope[A2aWorkspaceRs])
async def put_a2a_workspace(
    body: A2aWorkspaceRq,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[A2aWorkspaceRs]:
    svc = SettingService(db)
    rc = svc.set_a2a_workspace(user.account_sn, user.login_id, body.path)
    if rc == 1:
        return fail(1, "path 가 비어있습니다.")  # type: ignore[return-value]
    return ok(A2aWorkspaceRs(path=body.path))


@router.get("/code-server", response_model=ApiEnvelope[CodeServerRs])
async def get_code_server(
    _user: AuthenticatedUser = Depends(current_user),
) -> ApiEnvelope[CodeServerRs]:
    url, alive = SettingService.get_code_server(settings_env.code_server_url)
    return ok(CodeServerRs(url=url, alive=alive))


@router.get("/workrole-file", response_model=ApiEnvelope[WorkroleFileRs])
async def get_workrole_file(
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[WorkroleFileRs]:
    svc = SettingService(db)
    return ok(WorkroleFileRs(path=svc.get_workrole_file(user.account_sn)))


@router.put("/workrole-file", response_model=ApiEnvelope[WorkroleFileRs])
async def put_workrole_file(
    body: WorkroleFileRq,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[WorkroleFileRs]:
    svc = SettingService(db)
    svc.set_workrole_file(user.account_sn, body.path)
    return ok(WorkroleFileRs(path=body.path or ""))
