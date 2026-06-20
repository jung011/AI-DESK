"""helper router — /api/helper/*. Spring HelperDownloadController 와 1:1.

- GET /version   : image 안 baked .pkg 의 latest + filename
- GET /download  : .pkg binary 서빙
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from app.auth.deps import current_user
from app.auth.schemas import AuthenticatedUser
from app.common.response import ApiEnvelope, ok
from app.core.config import get_settings
from app.helper.service import extract_version, locate_pkg

router = APIRouter()
settings_env = get_settings()


@router.get("/_health")
async def health() -> dict[str, str]:
    return {"router": "helper", "status": "ok"}


@router.get("/version", response_model=ApiEnvelope[dict])
async def version(
    _user: AuthenticatedUser = Depends(current_user),
) -> ApiEnvelope[dict]:
    """frontend 의 helperVersionStore 가 호출 — running 과 비교해 업데이트 배너."""
    pkg = locate_pkg(settings_env.helper_pkg_dir)
    if pkg is None:
        return ok({"latest": "", "filename": ""})
    filename = pkg.name
    return ok({"latest": extract_version(filename), "filename": filename})


@router.get("/download")
async def download(
    _user: AuthenticatedUser = Depends(current_user),
):
    """image 안 .pkg 를 attachment 로 서빙. 한글/공백 포함 대비 RFC 5987 filename*."""
    pkg = locate_pkg(settings_env.helper_pkg_dir)
    if pkg is None:
        return JSONResponse(status_code=404, content={"result": 404, "message": "no .pkg", "data": None})
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
