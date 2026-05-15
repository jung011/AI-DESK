"""중앙 백엔드의 `/api/desktop/events` SSE 채널을 구독해 메시지 last-mile 을 수행.

이벤트 `message.deliver` 수신 시 본인 Mac 의 tmux 세션에 send-keys.
백엔드는 macOS 종속 코드 제거 — Docker 컨테이너 안에서도 동일하게 동작.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
from httpx_sse import aconnect_sse

log = logging.getLogger(__name__)

# 백엔드 TmuxLastMileAdapter 와 동일한 렌더 포맷 (adesk_cli.md 와 정합).
_HEADER_TEMPLATE = (
    "[aidesk · FROM:{from_name} | MSG:{msg_id}] {content}"
    "  ↳ 응답: adesk reply {msg_id} '<답변>'"
)
# Claude TUI 가 bracketed-paste 로 Enter 를 흡수하지 않도록 분리 송신 사이 짧은 지연.
_ENTER_DELAY_SEC = 0.2


def _render_message(payload: dict) -> str:
    return _HEADER_TEMPLATE.format(
        from_name=payload.get("fromAgentName", ""),
        msg_id=payload.get("messageId", ""),
        content=payload.get("content", ""),
    )


async def _tmux_has_session(session: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "has-session",
            "-t",
            session,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        return rc == 0
    except OSError:
        return False


async def _tmux_send(session: str, text: str) -> bool:
    """`tmux send-keys -l` 로 텍스트 + 짧은 지연 + 별도 Enter — 백엔드와 동일 패턴."""
    try:
        p1 = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-l", "-t", session, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc1 = await p1.wait()
        if rc1 != 0:
            return False
        await asyncio.sleep(_ENTER_DELAY_SEC)
        p2 = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-t", session, "Enter",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc2 = await p2.wait()
        return rc2 == 0
    except OSError as e:
        log.warning("tmux send-keys failed: %s", e)
        return False


async def _handle_message_deliver(payload: dict) -> None:
    session = (payload.get("toTmuxSession") or "").strip()
    if not session:
        log.warning("message.deliver: empty toTmuxSession, dropping")
        return
    if not await _tmux_has_session(session):
        log.info("message.deliver: target session %s not on this Mac — ignored", session)
        return
    rendered = _render_message(payload)
    ok = await _tmux_send(session, rendered)
    log.info(
        "message.deliver: session=%s msg=%s ok=%s",
        session,
        payload.get("messageId"),
        ok,
    )


async def _consume_once(backend_url: str) -> None:
    url = f"{backend_url.rstrip('/')}/api/desktop/events"
    timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with aconnect_sse(client, "GET", url) as event_source:
            log.info("SSE connected: %s", url)
            async for sse in event_source.aiter_sse():
                if sse.event != "message.deliver":
                    log.debug("SSE skip event: %s", sse.event)
                    continue
                try:
                    payload = sse.json()
                except json.JSONDecodeError:
                    log.warning("SSE payload not JSON: %r", sse.data[:200])
                    continue
                # blocking 안 되게 별도 태스크로
                asyncio.create_task(_handle_message_deliver(payload))


async def consumer_loop(backend_url: str) -> None:
    """끊김 / 백엔드 재기동 등에 대비해 무한 재연결."""
    backoff = 1.0
    while True:
        try:
            await _consume_once(backend_url)
            backoff = 1.0  # 정상 종료시 (서버가 close 했을 때) backoff 리셋
        except (httpx.HTTPError, OSError) as e:
            log.warning("SSE loop disconnected: %s (retry in %.1fs)", e, backoff)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — 어떤 예외도 루프를 멈추지 못하게
            log.exception("SSE loop iteration crashed: %s (retry in %.1fs)", e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)  # 지수 백오프, 최대 30초
