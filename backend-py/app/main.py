"""FastAPI entry — router 등록 + middleware + exception handler.

AI Desk backend (FastAPI 마이그). Spring Boot 의 대체.
"""
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
    from app.agents.watcher import start as start_watcher
    watcher_task = start_watcher()
    try:
        yield
    finally:
        watcher_task.cancel()
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

# /static/mcp — 외부 AI mcp standalone binary 배포 (git 없는 운영 환경 대상).
# binary 는 backend-py/static/mcp/ 에 baked. 외부 AI 가 curl 로 다운로드 + chmod +x + 실행.
# 예: curl -o aidesk-channel-mcp http://aidesk.kaflix.internal/static/mcp/aidesk-channel-mcp-linux-x64
from pathlib import Path as _Path  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_static_dir = _Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
    log.info("static mount: %s", _static_dir)
else:
    log.warning("static dir missing — skipping mount: %s", _static_dir)
