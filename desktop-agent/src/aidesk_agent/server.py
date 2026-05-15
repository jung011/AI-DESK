"""AI Desk Desktop Agent — aiohttp 기반 로컬 HTTP 리스너.

브라우저(중앙 호스팅 대시보드) ↔ 로컬 OS 사이의 IPC 다리 역할.
비즈니스 로직은 중앙 백엔드(Spring Boot) 가 담당하고, 본 모듈은 본인 Mac
자원만 조작한다.
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from . import __version__
from .claude_scanner import scan_workspaces
from .reporter import DEFAULT_BACKEND_URL, DEFAULT_REPORT_INTERVAL_SEC, reporter_loop
from .tmux_scanner import scan_sessions

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 30083


async def health(_: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "version": __version__,
            "service": "aidesk-agent",
        }
    )


async def local_info(_: web.Request) -> web.Response:
    """이 Mac 의 로컬 Claude 워크스페이스 + tmux 세션 스냅샷."""
    workspaces = [w.as_dict() for w in scan_workspaces()]
    tmux = [s.as_dict() for s in scan_sessions()]
    return web.json_response(
        {
            "workspaces": workspaces,
            "tmuxSessions": tmux,
        }
    )


async def _start_reporter(app: web.Application) -> None:
    backend_url = os.environ.get("AIDESK_BACKEND_URL", DEFAULT_BACKEND_URL)
    interval = float(
        os.environ.get("AIDESK_REPORT_INTERVAL_SEC", DEFAULT_REPORT_INTERVAL_SEC)
    )
    log.info("reporter starting: backend=%s interval=%.1fs", backend_url, interval)
    app["reporter_task"] = asyncio.create_task(reporter_loop(backend_url, interval))


async def _stop_reporter(app: web.Application) -> None:
    task = app.get("reporter_task")
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/local-info", local_info)
    app.on_startup.append(_start_reporter)
    app.on_cleanup.append(_stop_reporter)
    return app


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    web.run_app(build_app(), host=host, port=port, access_log=None)
