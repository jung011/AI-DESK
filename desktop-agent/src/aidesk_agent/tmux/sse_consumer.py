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

from ..watchdog import mark_sse_event

log = logging.getLogger(__name__)

# 백엔드 TmuxLastMileAdapter 와 동일한 렌더 포맷 (adesk_cli.md 와 정합).
_HEADER_TEMPLATE = (
    "[aidesk · FROM:{from_name} | MSG:{msg_id}] {content}"
    "  ↳ 응답: adesk reply {msg_id} '<답변>'"
)
# Claude TUI 가 bracketed-paste 로 Enter 를 흡수하지 않도록 분리 송신 사이 지연.
# 최근 claude code update 후 옛 200ms + "Enter" 패턴에서 Enter 흡수 → 500ms + raw "C-m"
# (carriage return) 으로 fix. C-m = terminal mode 무관 raw \r byte → paste mode 우회.
_ENTER_DELAY_SEC = 0.5

# 같은 tmux 세션으로 가는 메시지를 직렬 처리하기 위한 큐.
# 여러 발신자가 동시에 같은 수신자로 보낼 때 tmux send-keys 가 race 해서
# 텍스트가 interleave 되거나 한 turn 에 묻혀 일부 메시지에 reply 가 안 가는 문제를 막는다.
_session_queues: dict[str, asyncio.Queue] = {}
_session_workers: dict[str, asyncio.Task] = {}

# PoC v1 Step B — 봇 어댑터가 담당한 tmux session 은 sse_consumer 가 last-mile 안 함.
# bootstrap.py 의 ensure_bot_adapter 가 spawn 성공 시 register_bot_adapter_session 호출 →
# 여기 set 에 추가. message.deliver 가 해당 session 향이면 skip (어댑터가 처리).
# 어댑터 spawn 실패 / 미동작 시엔 set 에 안 들어가 sse_consumer 가 그대로 fallback.
_bot_adapter_sessions: set[str] = set()


def register_bot_adapter_session(session: str) -> None:
    """봇 어댑터가 담당하기 시작한 tmux session 을 등록 — sse_consumer 가 그 session 제외."""
    _bot_adapter_sessions.add(session)
    log.info("[sse-consumer] bot-adapter session registered — skip last-mile here: %s", session)


def unregister_bot_adapter_session(session: str) -> None:
    """봇 어댑터 종료 시 등록 해제 — sse_consumer 가 fallback 으로 다시 처리."""
    _bot_adapter_sessions.discard(session)
    log.info("[sse-consumer] bot-adapter session unregistered — fallback to sse_consumer: %s", session)
# send-keys 직후 다음 메시지를 보내기까지의 grace — claude 가 첫 입력을 prompt 로
# 인식하고 처리 시작할 시간. 너무 짧으면 두 번째 메시지가 현재 turn 의 추가 input 으로
# 묻힘. 0.5s 면 일반 케이스 충분.
_QUEUE_GRACE_SEC = 0.5


def _render_message(payload: dict) -> str:
    content = payload.get("content", "")
    attachments = payload.get("attachments") or []
    if attachments:
        # 채팅 첨부 (옵션 A) — backend가 보낸 attachments[] 를 tmux 텍스트 라인으로 append.
        # AI 는 path 만 보고 본인 backend host 와 합성해 GET 으로 다운로드. URL prefix 는
        # AI 환경마다 다를 수 있어 helper 가 host 까지 박지 않음.
        lines = []
        for a in attachments:
            aid = a.get("attachmentId", "")
            name = a.get("originalFilename", "")
            size = a.get("sizeBytes", 0)
            lines.append(f"📎 첨부 {name} ({size}b) — GET /api/attachments/{aid}")
        content = content + "\n" + "\n".join(lines)
    return _HEADER_TEMPLATE.format(
        from_name=payload.get("fromAgentName", ""),
        msg_id=payload.get("messageId", ""),
        content=content,
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
            "tmux", "send-keys", "-t", session, "C-m",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc2 = await p2.wait()
        return rc2 == 0
    except OSError as e:
        log.warning("tmux send-keys failed: %s", e)
        return False


async def _send_ack(backend_url: str, message_id: str) -> None:
    """tmux send-keys 가 도달했음을 backend 에 통보 — end-to-end ACK.

    backend 는 이걸 받아야 status='delivered' 마킹. ACK 가 실패하면 backend retry 가
    같은 메시지를 다시 발송하므로 *사용자 터미널에 같은 메시지가 두 번 박히는 storm* 의
    원인이 된다. 한 번의 일시 hang/slow 응답으로 storm 이 발생하지 않도록:
      - timeout 을 10s 로 늘려 backend 지연 (.local TLD 해석 지연, network 일시 정체 등) 흡수
      - 첫 시도 실패 시 3초 후 1회 재시도. 둘 다 실패해야 backend retry 에 위임.
    """
    if not message_id:
        return
    url = f"{backend_url.rstrip('/')}/api/messages/{message_id}/ack"
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url)
                log.info("[message-ack] sent msg=%s http=%s attempt=%d",
                         message_id, r.status_code, attempt + 1)
                return
        except (httpx.HTTPError, OSError) as e:
            if attempt == 0:
                log.warning("[message-ack] attempt 1 failed msg=%s err=%s — retrying in 3s",
                            message_id, e)
                await asyncio.sleep(3.0)
                continue
            log.warning("[message-ack] FAILED msg=%s err=%s — backend retry 가 처리할 것",
                        message_id, e)


async def _session_worker(session: str, backend_url: str) -> None:
    """session 별 worker — 큐의 메시지를 직렬 처리.

    다음 메시지를 보내기 전 짧은 grace 를 두어 claude 가 첫 입력을 처리 시작할
    시간을 확보. 그래야 후속 메시지가 *현재 turn 의 추가 input* 으로 묻히지 않음.
    """
    q = _session_queues[session]
    while True:
        payload = await q.get()
        try:
            await _handle_message_deliver(payload, backend_url)
        except Exception as e:
            log.exception("[session-queue] handler crashed session=%s err=%s", session, e)
        await asyncio.sleep(_QUEUE_GRACE_SEC)
        q.task_done()


async def _enqueue_for_session(session: str, payload: dict, backend_url: str) -> None:
    """같은 tmux session 향 메시지는 큐로 직렬화. 새 session 발견 시 worker spawn."""
    if session not in _session_queues:
        _session_queues[session] = asyncio.Queue()
        _session_workers[session] = asyncio.create_task(
            _session_worker(session, backend_url)
        )
        log.info("[session-queue] worker spawned session=%s", session)
    await _session_queues[session].put(payload)


async def _handle_message_deliver(payload: dict, backend_url: str) -> None:
    """B Phase 5 (dev 브랜치 Channels 통일 정책) — last-mile 책임 mcp(bun) Channels 로 이관.

    sse_consumer 의 옛 책임 = tmux send-keys + ack. 변경:
      - send-keys 제거 — Channels inject 가 유일한 last-mile.
      - ack 도 mcp 가 책임 — sse_consumer 는 ack 안 함.
      - 본 함수는 *SSE liveness keep-alive* 역할만 (event 수신 자체 = watchdog
        의 _last_sse_event_at 갱신 — _consume_once 의 mark_sse_event 가 처리).
    """
    session = (payload.get("toTmuxSession") or "").strip()
    message_id = payload.get("messageId") or ""
    log.debug(
        "message.deliver: session=%s msg=%s — skip (Channels last-mile)",
        session, message_id,
    )


async def _consume_once(backend_url: str) -> None:
    # rc20 — SSE recipient 별 filter. backend 가 현재 mac 의 tmux session 매칭 event 만 push.
    # outer loop 의 reconnect (2분 마다 ReadTimeout) 시 *현재 tmux 다시 scan* 으로 filter 자동 갱신.
    from urllib.parse import quote
    from ..tmux import scan_sessions
    try:
        sessions = scan_sessions()
        tmux_names = sorted({s.name for s in sessions if s.name})
    except Exception:  # noqa: BLE001 — scan 실패 시 빈 filter (broadcast 모드 fallback)
        tmux_names = []
    base = f"{backend_url.rstrip('/')}/api/desktop/events"
    if tmux_names:
        url = base + "?filter=" + quote(",".join(tmux_names), safe="")
    else:
        url = base
    # VPN / 사외 LAN 환경에서 라우터가 idle TCP 를 silent 끊어도 read=None 이면
    # zombie connection 으로 영원히 wait — deliver event 누락. read timeout 으로
    # N초 event 없으면 ReadTimeout 발생 → 바깥의 consumer_loop 가 자동 reconnect.
    # 120s = VPN 일반 idle timeout (5~10분) 보다 짧아 zombie 발생 전 갱신.
    timeout = httpx.Timeout(connect=5.0, read=120.0, write=5.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with aconnect_sse(client, "GET", url) as event_source:
            log.info("SSE connected: %s", url)
            mark_sse_event()  # 연결 직후 idle timer 리셋 — watchdog 의 false-positive 방지
            async for sse in event_source.aiter_sse():
                mark_sse_event()  # 어떤 event 든 (heartbeat comment / message.deliver) 갱신
                if sse.event != "message.deliver":
                    log.debug("SSE skip event: %s", sse.event)
                    continue
                try:
                    payload = sse.json()
                except json.JSONDecodeError:
                    log.warning("SSE payload not JSON: %r", sse.data[:200])
                    continue
                # 같은 tmux session 으로 가는 메시지는 직렬 처리 — race + interleave 방지.
                # 빈 session 이면 _handle_message_deliver 가 알아서 drop 하니까 그쪽으로 직접 넘김.
                target_session = (payload.get("toTmuxSession") or "").strip()
                if target_session:
                    asyncio.create_task(
                        _enqueue_for_session(target_session, payload, backend_url)
                    )
                else:
                    asyncio.create_task(_handle_message_deliver(payload, backend_url))


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
