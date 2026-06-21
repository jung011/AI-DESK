"""FastAPI entry — router 등록 + middleware + exception handler.

AI Desk backend (FastAPI 마이그). Spring Boot 의 대체.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.external.router import router as agents_external_router
from app.agents.router import router as agents_router
from app.auth.router import router as auth_router
from app.colleagues.router import router as colleagues_router
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middlewares
from app.desktop.router import router as desktop_router
from app.helper.router import router as helper_router
from app.logs.router import router as logs_router
from app.messages.attachment_router import router as attachments_router
from app.messages.router import router as messages_router
from app.settings.router import router as settings_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    force=True,  # uvicorn 의 default handler override — app.* logger 가 stdout 으로 propagate 보장 (rc12).
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """app startup / shutdown — agent status watcher 등 백그라운드 task."""
    log.info("aidesk-backend starting")

    # alembic upgrade head — schema 변경을 *정식 migration* 으로 적용.
    # idempotent (이미 적용된 migration 은 noop). DB 권한 부족 시 warning + 진행.
    try:
        from alembic import command
        from alembic.config import Config
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        log.info("startup: alembic upgrade head — OK")
    except Exception as e:  # noqa: BLE001
        log.warning("startup: alembic upgrade failed — %s", e)

    from app.agents.watcher import start as start_watcher
    watcher_task = start_watcher()

    # helper-pkg 새 image 가 swap 되면 사용자 frontend 가 즉시 banner 갱신하도록 SSE event.
    # 5초 지연 = frontend EventSource 가 reconnect 후 subscribe 완료할 시간 확보.
    async def _publish_helper_version_after_warmup() -> None:
        import asyncio as _asyncio
        from app.helper.service import locate_pkg, extract_version
        from app.messages.sse import broker as _broker
        await _asyncio.sleep(5)
        try:
            pkg = locate_pkg()
            version = extract_version(pkg) if pkg else None
            if version:
                _broker.publish("helper.version.changed", {"version": version})
                log.info("startup: helper.version.changed broadcast — version=%s", version)
        except Exception:  # noqa: BLE001
            log.exception("startup: helper version publish failed")

    helper_task = asyncio.create_task(_publish_helper_version_after_warmup(), name="helper-version-publish")

    try:
        yield
    finally:
        # cancel + await — cancel 만 호출하면 task 가 중간 자원 들고 있을 수 있어
        # await 로 정리 완료 확인 (CancelledError 흡수).
        for task in (watcher_task, helper_task):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        log.info("aidesk-backend stopping")


app = FastAPI(
    title="AI Desk API",
    description="AI Desk backend — FastAPI",
    version="0.1.0",
    lifespan=lifespan,
)

register_middlewares(app)
register_exception_handlers(app)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    """K8s liveness / readiness probe."""
    return {"status": "ok", "service": "aidesk-backend"}


# 도메인별 router 등록 — 순서는 endpoint 카탈로그 의 그룹에 맞춤.
app.include_router(auth_router,             prefix="/api/auth",            tags=["auth"])
app.include_router(agents_router,           prefix="/api/agents",          tags=["agents"])
app.include_router(agents_external_router,  prefix="/api/agents/external", tags=["agents-external"])
app.include_router(messages_router,         prefix="/api/messages",        tags=["messages"])
app.include_router(attachments_router,      prefix="/api/attachments",     tags=["attachments"])
app.include_router(desktop_router,          prefix="/api/desktop",         tags=["desktop"])
app.include_router(helper_router,           prefix="/api/helper",          tags=["helper"])
app.include_router(colleagues_router,       prefix="/api/colleagues",      tags=["colleagues"])
app.include_router(settings_router,         prefix="/api/settings",        tags=["settings"])
# logs router 는 /api/action-logs + /api/logs 두 path 처리 — prefix 안 채우고 root mount
app.include_router(logs_router,             prefix="/api",                 tags=["logs"])

# WebSocket /ws/messages — Spring 1:1. 3경로 인증 (cookie JWT / ?agentId / ?token Bearer).
# 외부 AI mcp 의 ws client + frontend dashboard 둘 다 사용.
from app.messages.ws import messages_ws_endpoint  # noqa: E402
app.add_api_websocket_route("/ws/messages", messages_ws_endpoint)

# /api/external/mcp — 외부 AI mcp standalone binary 배포 (git 없는 운영 환경 대상).
# binary 는 backend-py/static/mcp/ 에 baked. 외부 AI 가 curl 로 다운로드 + chmod +x + 실행.
# 예: curl -o aidesk-channel-mcp http://aidesk.kaflix.internal/api/external/mcp/aidesk-channel-mcp-linux-x64
# /api/ prefix = ingress 가 backend 로 routing (frontend 의 /static/* fallback 회피).
from pathlib import Path as _Path  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_static_dir = _Path(__file__).resolve().parent.parent / "static" / "mcp"
if _static_dir.is_dir():
    app.mount("/api/external/mcp", StaticFiles(directory=str(_static_dir)), name="external-mcp")
    log.info("external mcp static mount: %s", _static_dir)
else:
    log.warning("static/mcp dir missing — skipping mount: %s", _static_dir)
