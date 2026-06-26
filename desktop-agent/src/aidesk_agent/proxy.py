"""Backend HTTP proxy — mcp daemon (bun) 의 외부 IP socket allocation 격리.

[[feedback-mcp-bun-external-connect-block]] 사고 = bun runtime 의 외부 IP fetch 가
macOS kernel state 누적 후 차단. helper (python aiohttp) 는 정상 동작 → mcp daemon 의
외부 통신을 helper 가 대신.

흐름:
  mcp(bun)  ──localhost──→ helper(python) ──외부──→ backend
            ✓ bun localhost 정상   ✓ python 외부 정상

HTTP proxy 만 — outbound (api/messages POST, agent CRUD 등). WS path 는 *B Phase 3
의 broker* (`/ws/messages-broker`) 로 대체됨 — ws_proxy_handler 삭제 (2026-06-26).
"""
from __future__ import annotations

import logging
import os

import aiohttp
from aiohttp import web

log = logging.getLogger(__name__)


# proxy 가 forward 할 대상 backend URL. helper 의 _resolve_hub_url() 와 동일 출처.
def _backend_base() -> str:
    return (
        os.environ.get("AIDESK_HUB_URL")
        or os.environ.get("AIDESK_BACKEND_URL")
        or "http://localhost:30081"
    ).rstrip("/")


# proxy 가 *통과시키지 않을* 헤더 (hop-by-hop + helper layer 가 직접 관리하는 것).
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "host",  # 새로운 host 로 변경됨 — pass 시 backend 가 거부 가능
    "content-length",  # aiohttp 가 다시 계산
}


async def http_proxy_handler(request: web.Request) -> web.StreamResponse:
    """/api/proxy/{path:.*} — 모든 HTTP method forward.

    mcp daemon (bun) 이 fetch(`http://127.0.0.1:30083/api/proxy/api/messages`) 호출 시
    helper 가 backend `/api/messages` 로 forward. body / query / headers / status 모두
    그대로 통과.
    """
    rest = request.match_info.get("rest", "")
    backend = _backend_base()
    # rest 가 / 로 시작 안 할 수 있어 명시 prefix
    target = f"{backend}/{rest.lstrip('/')}"
    if request.query_string:
        target = f"{target}?{request.query_string}"

    # 헤더 사본 — hop-by-hop 제거. Authorization / X-* 등은 통과.
    fwd_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }

    # body — read 한 번 (모든 method 통합). multipart 도 OK.
    body = await request.read()

    timeout = aiohttp.ClientTimeout(total=60.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                request.method,
                target,
                headers=fwd_headers,
                data=body if body else None,
                allow_redirects=False,
            ) as up:
                # response 헤더도 hop-by-hop 제거 후 그대로 전달
                resp_headers = {
                    k: v for k, v in up.headers.items()
                    if k.lower() not in _HOP_BY_HOP
                }
                content = await up.read()
                return web.Response(
                    body=content,
                    status=up.status,
                    headers=resp_headers,
                )
    except aiohttp.ClientError as e:
        log.warning("proxy: backend error %s %s: %s", request.method, target, e)
        return web.json_response(
            {"result": -1, "message": f"helper proxy upstream error: {e}"},
            status=502,
        )


# ws_proxy_handler 는 2026-06-26 삭제. B Phase 3 의 broker (`/ws/messages-broker`) 로
# 대체됨. mcp(bun) 가 helper broker 로 직접 connect — helper proxy ws transparent
# forward 불필요.
