"""agents watcher — Spring AgentStatusWatcher 와 동등. asyncio task.

helper reporter 가 30초 cycle 로 status 갱신. 그 cycle 동안 못 받으면 stale.
60초 안 idle/active 인데 updated_at 안 변하면 'offline' 으로 강등.

별도 lifespan task 로 main.py 에서 등록/정리.
"""
import asyncio
import logging
from typing import Any

from app.agents.repository import AgentRepository
from app.core.database import SessionLocal

log = logging.getLogger(__name__)

# helper reporter 30s + 약간 여유 → 90s 안 신호 없으면 stale.
STALE_THRESHOLD_SECONDS = 90
# 한 cycle 마다 check 주기.
CHECK_INTERVAL_SECONDS = 30


async def _check_once() -> int:
    """stale agent 를 active → idle 강등. 갱신된 row 수 반환.

    rc19 design 정정 — idle = 살아있는 상태, offline ≠ idle. watcher 는 *active* 만
    *idle* 으로 강등 (생존 신호 끊김, 그러나 살아있다 가정). offline 마킹은 helper 의
    명시적 종료 보고 (tmux session 없음) 또는 agent delete 만.
    """
    db = SessionLocal()
    try:
        repo = AgentRepository(db)
        stale = repo.list_stale_active(STALE_THRESHOLD_SECONDS)
        log.info("watcher: tick threshold=%ds stale_candidates=%d", STALE_THRESHOLD_SECONDS, len(stale))
        if not stale:
            return 0
        updated = 0
        for agent in stale:
            n = repo.update_status_from_watcher(agent.agent_id, "idle")
            if n > 0:
                updated += 1
                log.info(
                    "watcher: agent=%s (id=%s type=%s) %s -> idle (stale, updated_at=%s)",
                    agent.agent_name, agent.agent_id, agent.agent_type,
                    agent.status, agent.updated_at,
                )
        db.commit()
        if updated > 0:
            log.info("watcher: tick complete — %d agent(s) demoted active->idle", updated)
        return updated
    finally:
        db.close()


async def _loop() -> None:
    while True:
        try:
            await _check_once()
        except Exception:  # noqa: BLE001 — 어떤 예외도 loop 멈추지 못하게
            log.exception("watcher: check failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start() -> asyncio.Task[Any]:
    """main.py lifespan startup 에서 호출. 반환 task 는 shutdown 시 cancel."""
    task = asyncio.create_task(_loop(), name="agent-status-watcher")
    log.info("agent watcher started — threshold=%ds interval=%ds", STALE_THRESHOLD_SECONDS, CHECK_INTERVAL_SECONDS)
    return task
