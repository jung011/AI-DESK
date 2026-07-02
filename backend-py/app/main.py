"""FastAPI entry — router 등록 + middleware + exception handler.

AI Desk backend (FastAPI 마이그). Spring Boot 의 대체.
"""
import asyncio
import logging
import os
import sys
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
from app.tasks.router import router as tasks_router

# 2026-07-02 진단 인프라 복구 — 3 시도 후 최종 fix (rc112 옵션 3).
#
# rc110 = module top-level 에서 root logger addHandler → uvicorn worker fork 시 clear. 실패.
# rc111 = lifespan startup 에서 root logger addHandler → uvicorn 이 그 이후에도 clear. 실패.
# rc112 = *root 우회* — `app` named logger 에 직접 handler + propagate=False.
#   uvicorn 은 root / uvicorn.* 만 조작하고 named custom logger 는 안 건드림.
#   `app.messages.service` / `app.core.middleware` 등 옛 코드의 모든 __name__ (=app.xxx)
#   가 hierarchy 로 `app` 을 부모 로 사용 → app handler 로 stdout 도달.
#   pre-verification 완료 (리키2 sanity test): logger('app.test.child').info → stdout 출력 확인.
_app_log = logging.getLogger("app")
_app_log.setLevel(logging.INFO)
_app_log.propagate = False  # root 우회 (uvicorn 조작 밖)
if not _app_log.handlers:
    _app_handler = logging.StreamHandler(sys.stdout)
    _app_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    _app_log.addHandler(_app_handler)

# root handler 도 함께 등록 (옛 rc110 유지, 무해) — root 사용하는 3rd-party lib 도 잡음.
_root = logging.getLogger()
_root.setLevel(logging.INFO)
if not _root.handlers:
    _root_handler = logging.StreamHandler(sys.stdout)
    _root_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    _root.addHandler(_root_handler)

log = logging.getLogger(__name__)  # 'app.main' — 새 app handler 통해 출력


@asynccontextmanager
async def lifespan(app: FastAPI):
    """app startup / shutdown — agent status watcher 등 백그라운드 task.

    추가 진단 — pod restart 의 *진짜 root* 잡기 위해:
    - startup 시 image tag + git sha + start time 명시 logging
    - shutdown 시 uptime + SIGTERM 수신 시각 logging
    이 신호 = K8s stdout 의 app log 에 박혀 사고 시 *언제 swap 박혔는지* 명확.
    """
    # 2026-07-02 rc112 — lifespan 안에서도 `app` named logger + root 둘 다 재확인.
    # rc111 은 root 만 재등록 → uvicorn 이 이후에도 clear 로 실패. rc112 는 `app`
    # 우회 + lifespan 안에서 둘 다 idempotent 재확인 (uvicorn 이 lifespan 이후 무엇을
    # 하든 named logger 는 안 건드림 = 안전 net).
    _app_l = logging.getLogger("app")
    _app_l.setLevel(logging.INFO)
    _app_l.propagate = False
    if not _app_l.handlers:
        _app_h = logging.StreamHandler(sys.stdout)
        _app_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        _app_l.addHandler(_app_h)
        logging.getLogger("app.main").info("rc112: app logger handler re-applied in lifespan")

    _root_l = logging.getLogger()
    _root_l.setLevel(logging.INFO)
    if not _root_l.handlers:
        _h = logging.StreamHandler(sys.stdout)
        _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        _root_l.addHandler(_h)
        logging.getLogger(__name__).info("rc111: root logger handler re-applied in lifespan")

    import time as _time
    global _STARTUP_EPOCH
    startup_epoch = _time.time()
    _STARTUP_EPOCH = startup_epoch
    image_tag = os.environ.get("IMAGE_TAG", "unknown")  # helm 에서 주입 (옵션)
    log.warning(
        "AIDESK_BACKEND_STARTUP — image_tag=%s pid=%d startup_epoch=%.3f",
        image_tag, os.getpid(), startup_epoch,
    )

    # alembic upgrade head — schema 변경을 *정식 migration* 으로 적용.
    # idempotent (이미 적용된 migration 은 noop). DB 권한 부족 시 warning + 진행.
    # AIDESK_SKIP_MIGRATIONS=1 — dev 환경 의 sqlite hang 회피 (alembic 의 sqlite
    # non-transactional DDL 에서 block 사고). prod 영향 X.
    if os.environ.get("AIDESK_SKIP_MIGRATIONS") != "1":
        try:
            from alembic import command
            from alembic.config import Config
            cfg = Config("alembic.ini")
            command.upgrade(cfg, "head")
            log.info("startup: alembic upgrade head — OK")
        except Exception as e:  # noqa: BLE001
            log.warning("startup: alembic upgrade failed — %s", e)
    else:
        log.info("startup: alembic upgrade SKIPPED (AIDESK_SKIP_MIGRATIONS=1)")

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
        # SIGTERM 진단 — pod 가 *언제 / 얼마 만에* 죽었는지 명시. 옛 사고 시 K8s log
        # 의 STARTUP / SHUTDOWN pair 박혀있어 *swap 빈도 / 원인* 분석 가능.
        shutdown_epoch = _time.time()
        uptime_sec = int(shutdown_epoch - startup_epoch)
        log.warning(
            "AIDESK_BACKEND_SHUTDOWN — image_tag=%s uptime_sec=%d shutdown_epoch=%.3f",
            image_tag, uptime_sec, shutdown_epoch,
        )


app = FastAPI(
    title="AI Desk API",
    description="AI Desk backend — FastAPI",
    version="0.1.0",
    lifespan=lifespan,
)

register_middlewares(app)
register_exception_handlers(app)


_STARTUP_EPOCH: float = 0.0  # lifespan startup 에서 박음 (옛 진단용)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, object]:
    """K8s liveness / readiness probe + 진단 정보.

    pod start 시점 / uptime 노출 — frontend 가 polling 박아 *pod swap 시점* 감지 가능.
    옛 사고 시 nav-debug 의 fetch trace 에 startup_epoch 변화 박혀 *언제 swap* 명확.
    """
    import time as _time
    return {
        "status": "ok",
        "service": "aidesk-backend",
        "image_tag": os.environ.get("IMAGE_TAG", "unknown"),
        "startup_epoch": _STARTUP_EPOCH,
        "uptime_sec": int(_time.time() - _STARTUP_EPOCH) if _STARTUP_EPOCH else 0,
        "pid": os.getpid(),
    }


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
app.include_router(tasks_router,            prefix="/api/tasks",           tags=["tasks"])
# logs router 는 /api/action-logs + /api/logs 두 path 처리 — prefix 안 채우고 root mount
app.include_router(logs_router,             prefix="/api",                 tags=["logs"])

# WebSocket /ws/messages — Spring 1:1. 3경로 인증 (cookie JWT / ?agentId / ?token Bearer).
# 외부 AI mcp 의 ws client + frontend dashboard 둘 다 사용.
from app.messages.ws import messages_ws_endpoint, messages_broker_ws_endpoint  # noqa: E402
app.add_api_websocket_route("/ws/messages", messages_ws_endpoint)
# B Phase 1 — helper broker endpoint. 한 ws 로 *여러 agent_id* subscribe (?agentIds=id1,id2,...).
# 옛 /ws/messages 와 *공존* — Phase 4 까지 호환 유지.
app.add_api_websocket_route("/ws/messages-broker", messages_broker_ws_endpoint)

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
