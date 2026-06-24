"""Backend proxy — mcp daemon (bun) 의 외부 IP socket allocation 격리.

[[feedback-mcp-bun-external-connect-block]] 사고 = bun runtime 의 외부 IP fetch 가
macOS kernel state 누적 후 차단. helper (python aiohttp) 는 정상 동작 → mcp daemon 의
외부 통신을 helper 가 대신.

흐름:
  mcp(bun)  ──localhost──→ helper(python) ──외부──→ backend
            ✓ bun localhost 정상   ✓ python 외부 정상

HTTP proxy + WebSocket proxy 둘 다 지원. mcp daemon 이 사용하는:
  - GET/POST /api/agents, /api/messages, ...
  - WS /ws/messages?agentId=...
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from urllib.parse import urlparse, urlunparse

import aiohttp
from aiohttp import web

log = logging.getLogger(__name__)


# === proxy liveness 마커 — watchdog 의 outbound 좀비 감지에 활용 ===
# proxy ws_proxy_handler 가 메시지 통과시킬 때마다 갱신. helper 가 backend 와 정상 통신 중이라는
# 신호. SSE consumer 의 _last_sse_event_at 와 *대등한 outbound liveness* 지표.
_last_proxy_event_at = time.monotonic()
_seen_first_proxy_event = False


def mark_proxy_event() -> None:
    """ws_proxy 가 메시지 통과시킬 때마다 호출. watchdog 의 outbound idle 판정에 사용."""
    global _last_proxy_event_at, _seen_first_proxy_event
    _last_proxy_event_at = time.monotonic()
    _seen_first_proxy_event = True


def time_since_proxy_event() -> float | None:
    """마지막 proxy ws event 후 경과 초. 한 번도 event 없었으면 None."""
    if not _seen_first_proxy_event:
        return None
    return time.monotonic() - _last_proxy_event_at

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


async def ws_proxy_handler(request: web.Request) -> web.WebSocketResponse:
    """/api/proxy/ws/{path:.*} — WebSocket bidirectional forward.

    mcp daemon 이 ws://127.0.0.1:30083/api/proxy/ws/messages?agentId=... 연결 시
    helper 가 backend ws://backend/ws/messages?agentId=... 로 forward + 양방향 message
    relay.
    """
    rest = request.match_info.get("rest", "")
    backend = _backend_base()
    # http → ws scheme 변환 + path 합치기
    parsed = urlparse(backend)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    target_url = urlunparse((
        ws_scheme, parsed.netloc, f"/ws/{rest.lstrip('/')}", "", request.query_string, ""
    ))

    # 1) downstream (mcp daemon ↔ helper) WS accept
    ws_down = web.WebSocketResponse()
    await ws_down.prepare(request)

    # 2) upstream (helper ↔ backend) WS connect
    try:
        session = aiohttp.ClientSession()
        ws_up = await session.ws_connect(target_url, heartbeat=30.0)
    except Exception as e:  # noqa: BLE001 — 연결 실패 시 downstream 도 닫음
        log.warning("proxy ws: upstream connect fail %s: %s", target_url, e)
        await ws_down.close(code=1011, message=str(e).encode())
        return ws_down

    log.info("proxy ws: connected — %s", target_url)
    # ws 연결 자체가 outbound liveness 신호 — watchdog 의 SSE idle 와 OR 관계.
    mark_proxy_event()

    async def pump_up_to_down() -> None:
        async for msg in ws_up:
            mark_proxy_event()
            if msg.type == aiohttp.WSMsgType.TEXT:
                await ws_down.send_str(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await ws_down.send_bytes(msg.data)
            elif msg.type == aiohttp.WSMsgType.CLOSE:
                await ws_down.close(code=msg.data or 1000)
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.warning("proxy ws upstream error: %s", ws_up.exception())
                break

    async def pump_down_to_up() -> None:
        async for msg in ws_down:
            mark_proxy_event()
            if msg.type == aiohttp.WSMsgType.TEXT:
                await ws_up.send_str(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await ws_up.send_bytes(msg.data)
            elif msg.type == aiohttp.WSMsgType.CLOSE:
                await ws_up.close(code=msg.data or 1000)
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                log.warning("proxy ws downstream error: %s", ws_down.exception())
                break

    try:
        await asyncio.gather(pump_up_to_down(), pump_down_to_up())
    except Exception:  # noqa: BLE001
        log.exception("proxy ws: pump fail")
    finally:
        try: await ws_up.close()
        except Exception: pass
        try: await ws_down.close()
        except Exception: pass
        await session.close()
        log.info("proxy ws: closed — %s", target_url)
    return ws_down
