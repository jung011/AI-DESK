"""로컬 kaflix-a2a 사이드카에서 본인 Mac 의 employeeId 를 알아낸다.

사이드카는 `/.well-known/agent.json` 으로 자신의 정체(agentCard) 를 노출하며,
거기에 `kaflix.employeeId` 가 포함되어 있다. Helper 는 시작 시 한 번 (또는 변경
감지가 필요하면 주기적으로) 이 값을 읽어 backend 보고에 동봉한다.

값을 못 알아내면 None 반환 — backend 는 application.yaml 의 me-employee-id
설정값을 fallback 으로 사용한다.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

DEFAULT_SIDECAR_URL = "http://localhost:9876"
_AGENT_CARD_PATH = "/.well-known/agent.json"


def detect_local_employee_id(sidecar_url: str = DEFAULT_SIDECAR_URL) -> str | None:
    """동기 호출로 사이드카 agentCard 를 받아 employeeId 를 추출."""
    url = f"{sidecar_url.rstrip('/')}{_AGENT_CARD_PATH}"
    try:
        resp = httpx.get(url, timeout=2.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.info("sidecar identity probe failed: %s (kaflix-a2a 미가동 또는 URL 변경)", e)
        return None
    try:
        card = resp.json()
    except ValueError:
        log.warning("sidecar agent.json 가 JSON 이 아님: %r", resp.text[:200])
        return None
    eid = (card.get("kaflix") or {}).get("employeeId")
    if isinstance(eid, str) and eid.strip():
        log.info("local employeeId 감지: %s (사이드카 %s)", eid, sidecar_url)
        return eid.strip()
    log.warning("sidecar agentCard 에 kaflix.employeeId 없음: %s", card.get("name"))
    return None
