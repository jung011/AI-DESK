"""사내 동료 AI(kaflix-channel) 의 인박스를 (me) liki tmux 로 자동 푸시.

흐름:
  외부 동료 PC 의 claude → kaflix-channel mcp.send_to(liki, ...)
    → 동료 사이드카 → Control Plane → 사용자 mac 의 사이드카
    → 사이드카 /channel/events SSE event 발행
    → 이 pump 가 구독해서 받음
    → (me) liki tmux 세션에 send-keys 로 떨굼
    → claude code 가 본문(<channel> 태그) 보고 자동 답장 가능

token 출처:
  (me) liki workspace 의 .mcp.json 안 kaflix-channel --token 인자에서 추출.
  helper 시작 시 backend(/api/agents) 로 (me) 워크스페이스 알아내고 거기서 token 읽음.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
from httpx_sse import aconnect_sse

log = logging.getLogger(__name__)

DEFAULT_SIDECAR_URL = "http://127.0.0.1:9876"
# tmux send-keys 와 Enter 사이 짧은 지연 — claude TUI 가 bracketed-paste 로 Enter 흡수 회피.
_ENTER_DELAY_SEC = 0.2


def _extract_token_from_workspace(workspace_dir: str) -> str | None:
    """workspace 의 .mcp.json 에서 kaflix-channel --token 값 추출."""
    mcp_path = Path(workspace_dir) / ".mcp.json"
    if not mcp_path.exists():
        return None
    try:
        d = json.loads(mcp_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.warning("kaflix token: %s 파싱 실패: %s", mcp_path, e)
        return None
    kc = d.get("mcpServers", {}).get("kaflix-channel", {})
    args = kc.get("args", []) or []
    for i, a in enumerate(args):
        if a == "--token" and i + 1 < len(args):
            return args[i + 1]
    return None


async def _tmux_send(session: str, text: str) -> bool:
    """tmux send-keys -l + 지연 + Enter — sse_consumer 와 동일 패턴."""
    try:
        p1 = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-l", "-t", session, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        if await p1.wait() != 0:
            return False
        await asyncio.sleep(_ENTER_DELAY_SEC)
        p2 = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-t", session, "Enter",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await p2.wait() == 0
    except OSError as e:
        log.warning("kaflix tmux send-keys failed: %s", e)
        return False


def _render(payload: dict) -> str:
    """사이드카 이벤트를 (me) 터미널에 떨굴 본문 형식.

    사이드카 binary 가 사용하는 사내 표준 <channel> 태그를 그대로 재구성.
    claude 가 <channel source="kaflix-channel"...> 를 보면 사내 동료 메시지로
    인식해 kaflix-channel mcp.reply 도구로 자동 응답 가능.
    """
    task_id = payload.get("taskId") or payload.get("task_id") or ""
    from_ = payload.get("from") or ""
    content = payload.get("content") or ""
    return (
        f'<channel source="kaflix-channel" task_id="{task_id}" from="{from_}">'
        f"{content}</channel>"
    )


async def _consume_once(sidecar_url: str, token: str, target_session: str) -> None:
    url = f"{sidecar_url.rstrip('/')}/channel/events"
    headers = {"x-kaflix-channel-token": token}
    timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with aconnect_sse(client, "GET", url, headers=headers) as event_source:
            log.info("kaflix SSE connected: %s -> %s", url, target_session)
            async for sse in event_source.aiter_sse():
                if not sse.data:
                    continue
                try:
                    payload = sse.json()
                except json.JSONDecodeError:
                    log.warning("kaflix SSE payload not JSON: %r", sse.data[:200])
                    continue
                rendered = _render(payload)
                ok = await _tmux_send(target_session, rendered)
                log.info(
                    "[kaflix-inbox] tmux=%s task=%s from=%s ok=%s",
                    target_session,
                    payload.get("taskId") or payload.get("task_id"),
                    payload.get("from"),
                    ok,
                )


async def _resolve_me_agent(backend_url: str) -> tuple[str, str] | None:
    """backend 에 (me) liki 의 workspace_dir + tmux_session 질의.

    (me) 식별: agentName 이 '(me)' 로 끝나는 row. helper 시작 시점에 backend 가
    아직 안 올라온 경우도 있어 짧은 retry.
    """
    url = f"{backend_url.rstrip('/')}/api/agents"
    for attempt in range(10):
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(url)
                r.raise_for_status()
                body = r.json()
                for a in body.get("data", {}).get("list", []):
                    name = a.get("agentName") or ""
                    if name.endswith("(me)") and a.get("tmuxSession") and a.get("workspaceDir"):
                        return a["workspaceDir"], a["tmuxSession"]
                log.info("kaflix pump: (me) agent 미확인, %d 회 재시도", attempt + 1)
        except (httpx.HTTPError, OSError) as e:
            log.info("kaflix pump: backend 응답 대기 %s (%d)", e, attempt + 1)
        await asyncio.sleep(2.0)
    return None


async def pump_loop(backend_url: str, sidecar_url: str = DEFAULT_SIDECAR_URL) -> None:
    """SSE 끊김/사이드카 재기동 등에 대비해 무한 재연결."""
    me = await _resolve_me_agent(backend_url)
    if me is None:
        log.warning("kaflix pump 비활성: (me) liki agent 를 backend 에서 찾지 못함")
        return
    workspace_dir, tmux_session = me
    token = _extract_token_from_workspace(workspace_dir)
    if not token:
        log.warning(
            "kaflix pump 비활성: %s 의 .mcp.json 에 kaflix-channel token 없음",
            workspace_dir,
        )
        return
    log.info("kaflix pump 시작: workspace=%s session=%s", workspace_dir, tmux_session)

    backoff = 1.0
    while True:
        try:
            await _consume_once(sidecar_url, token, tmux_session)
            backoff = 1.0
        except (httpx.HTTPError, OSError) as e:
            log.warning("kaflix SSE disconnected: %s (retry in %.1fs)", e, backoff)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — 어떤 예외도 루프를 멈추지 못하게.
            log.exception("kaflix SSE iteration crashed: %s (retry in %.1fs)", e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)
