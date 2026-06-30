"""helper router — /api/helper/*. Spring HelperDownloadController 와 1:1.

- GET /version   : image 안 baked .pkg(mac) / .zip(win) 의 latest + filename
- GET /download  : helper binary 서빙 (?os=win → .zip, 그 외 → .pkg)
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse

from app.auth.deps import current_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, ok
from app.core.config import get_settings
from app.helper.lan_ip_store import store as lan_ip_store
from app.helper.service import extract_version, locate_pkg

router = APIRouter()
settings_env = get_settings()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "helper", "status": "ok"}


@router.get("/version", response_model=ApiEnvelope[dict])
async def version(
    os: str = Query("mac", pattern="^(mac|win)$"),
    _user: AuthenticatedUser = Depends(current_user),
) -> ApiEnvelope[dict]:
    """frontend 의 helperVersionStore 가 호출 — running 과 비교해 업데이트 배너."""
    pkg = locate_pkg(settings_env.helper_pkg_dir, os)
    if pkg is None:
        return ok({"latest": "", "filename": ""})
    filename = pkg.name
    return ok({"latest": extract_version(filename), "filename": filename})


@router.get("/lan-ip", response_model=ApiEnvelope[dict])
async def lan_ip(user: AuthenticatedUser = Depends(current_user)) -> ApiEnvelope[dict]:
    """옵션 B MVP — auth 박힌 user 의 helper 가 박은 LAN IP 반환.

    모바일 frontend 가 *같은 wifi 안* 사용자 mac 의 helper 한테 직접 접근 박을 때 사용.
    helper 가 30s cycle 의 /api/desktop/local-info payload 안 lan_ip 박으면 store 갱신.
    """
    ip = lan_ip_store.get(user.account_sn)
    return ok({"lanIp": ip or ""})


@router.get("/download")
async def download(
    os: str = Query("mac", pattern="^(mac|win)$"),
    _user: AuthenticatedUser = Depends(current_user),
):
    """helper 패키지를 attachment 로 서빙 (?os=win → .zip, 그 외 → .pkg).
    한글/공백 포함 대비 RFC 5987 filename*."""
    pkg = locate_pkg(settings_env.helper_pkg_dir, os)
    if pkg is None:
        return JSONResponse(status_code=404, content={"result": 404, "message": "no helper pkg", "data": None})
    filename = pkg.name
    encoded = quote(filename, safe="")
    return FileResponse(
        path=str(pkg),
        media_type="application/octet-stream",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded}',
        },
    )
