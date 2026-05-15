"""중앙 백엔드로 로컬 스냅샷을 주기적으로 POST 하는 백그라운드 태스크."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .claude_scanner import scan_workspaces
from .tmux_scanner import scan_sessions

log = logging.getLogger(__name__)

# 1단계 PoC 기본값. 백엔드 주소는 환경변수로 override 가능.
DEFAULT_BACKEND_URL = "http://localhost:30081"
DEFAULT_REPORT_INTERVAL_SEC = 30.0


def build_payload() -> dict:
    return {
        "workspaces": [w.as_dict() for w in scan_workspaces()],
        "tmuxSessions": [s.as_dict() for s in scan_sessions()],
    }


async def send_once(client: httpx.AsyncClient, backend_url: str) -> dict | None:
    payload = build_payload()
    try:
        resp = await client.post(
            f"{backend_url.rstrip('/')}/api/desktop/local-info",
            json=payload,
            timeout=5.0,
        )
        resp.raise_for_status()
        body = resp.json()
        log.info(
            "reported: workspaces=%d tmux=%d → matched=%s updated=%s",
            len(payload["workspaces"]),
            len(payload["tmuxSessions"]),
            body.get("data", {}).get("matchedAgents"),
            body.get("data", {}).get("updatedAgents"),
        )
        return body
    except httpx.HTTPError as e:
        log.warning("report failed: %s", e)
        return None


async def reporter_loop(backend_url: str, interval_sec: float) -> None:
    # 매 호출마다 새 client — 네트워크 변경(Mac sleep/wake) 후 stale connection 회피.
    # 30초 단위 폴링이라 신규 client 비용은 무시 가능 (백엔드 ExternalAgentService 와 같은 패턴).
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await send_once(client, backend_url)
        except Exception as e:  # noqa: BLE001 — 어떤 예외도 루프를 멈추지 못하게.
            log.warning("reporter loop iteration failed: %s", e)
        await asyncio.sleep(interval_sec)
