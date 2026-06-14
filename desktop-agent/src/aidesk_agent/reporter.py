"""중앙 백엔드로 로컬 스냅샷을 주기적으로 POST 하는 백그라운드 태스크."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .claude import scan_workspaces
from .tmux import scan_sessions

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
    """30초 cycle 1회의 reporter 호출. 한 번 fail 만으로 backend 의 lastSeen 이 stale 되어
    옵션 1 markFailed (`수신자 helper 오프라인`) 가 false-positive 로 발동하는 것을 막기 위해,
    HTTP fail (DNS jitter / network blip 등) 시 3초 후 *1회 즉시 retry*. 두 번 다 실패해야
    skip — 다음 30초 cycle 까지 lastSeen 갱신 X."""
    payload = build_payload()
    for attempt in range(2):
        try:
            resp = await client.post(
                f"{backend_url.rstrip('/')}/api/desktop/local-info",
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            body = resp.json()
            log.info(
                "reported: workspaces=%d tmux=%d → matched=%s updated=%s attempt=%d",
                len(payload["workspaces"]),
                len(payload["tmuxSessions"]),
                body.get("data", {}).get("matchedAgents"),
                body.get("data", {}).get("updatedAgents"),
                attempt + 1,
            )
            return body
        except httpx.HTTPError as e:
            if attempt == 0:
                log.warning("report attempt 1 failed: %s — retrying in 3s", e)
                await asyncio.sleep(3.0)
                continue
            log.warning("report failed (both attempts): %s", e)
            return None
    return None


async def reporter_loop(backend_url: str, interval_sec: float) -> None:
    # 매 호출마다 새 client — 네트워크 변경(Mac sleep/wake) 후 stale connection 회피.
    # 30초 단위 폴링이라 신규 client 비용은 무시 가능.
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await send_once(client, backend_url)
        except Exception as e:  # noqa: BLE001 — 어떤 예외도 루프를 멈추지 못하게.
            log.warning("reporter loop iteration failed: %s", e)
        await asyncio.sleep(interval_sec)
