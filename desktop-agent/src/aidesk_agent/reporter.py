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
                body = await send_once(client, backend_url)
                # B Phase 2 — broker 의 subscribe list 동기화. local-info response 의
                # matchedAgentIds 가 *이 mac 이 hosting 중인 agent_id 목록*. broker 가
                # backend ws 의 ?agentIds= 에 사용.
                if body is not None:
                    _sync_broker_subscribe(body)
        except Exception as e:  # noqa: BLE001 — 어떤 예외도 루프를 멈추지 못하게.
            log.warning("reporter loop iteration failed: %s", e)
        await asyncio.sleep(interval_sec)


def _sync_broker_subscribe(body: dict) -> None:
    """reporter response 의 matchedAgentIds 를 broker 로 전달.

    broker singleton 은 server.py 의 app["broker"] 에 박혀있음 — 직접 import 하면
    순환. server module 의 _LATEST_BROKER (module global) 로 우회. broker.start()
    시점에 설정.
    """
    try:
        from . import server as _server  # noqa: PLC0415
        broker = getattr(_server, "_LATEST_BROKER", None)
        if broker is None:
            return
        agent_ids = body.get("data", {}).get("matchedAgentIds") or []
        if isinstance(agent_ids, list):
            broker.update_subscribed_ids([str(a) for a in agent_ids if a])
    except Exception as e:  # noqa: BLE001
        log.warning("reporter: broker subscribe sync failed: %s", e)
