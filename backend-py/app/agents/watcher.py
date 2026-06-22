"""agents watcher — Spring AgentStatusWatcher 와 동등. asyncio task.

helper reporter 가 30초 cycle 로 status 갱신. 그 cycle 동안 못 받으면 stale.
60초 안 idle/active 인데 updated_at 안 변하면 'offline' 으로 강등.

별도 lifespan task 로 main.py 에서 등록/정리.
"""
import asyncio
import logging
import os
from typing import Any

from app.agents.repository import AgentRepository
from app.core.database import SessionLocal
from app.messages.ws import ws_broker

log = logging.getLogger(__name__)

# helper reporter 30s + 약간 여유 → 90s 안 신호 없으면 stale.
# rc47 — ConfigMap env 로 운영 중 조정 가능 (leak 사고 시 cycle 늘려 단기 완화).
STALE_THRESHOLD_SECONDS = int(os.environ.get("AIDESK_WATCHER_STALE_THRESHOLD_SECONDS", "90"))
# 한 cycle 마다 check 주기.
CHECK_INTERVAL_SECONDS = int(os.environ.get("AIDESK_WATCHER_CHECK_INTERVAL_SECONDS", "30"))


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
    except Exception:
        # rollback 누락 시 transaction 이 abort 상태로 pool 에 반환되어 idle in transaction
        # 누적 → pool 고갈 (rc24 사고 fix).
        db.rollback()
        log.exception("watcher: rolled back transaction")
        raise
    finally:
        db.close()


async def _touch_ws_active_once() -> int:
    """ws session 활성 agent 의 updated_at 갱신 — colleague online window (5분) 유지용.

    외부 AI 는 helper reporter 없어 stale 만으로 회색이 됨. ws connect 살아있는 동안
    backend 가 주기 touch → updated_at fresh → ColleagueService 의 5분 window 안 유지.
    내부 봇은 helper 30s reporter 가 이미 touch 하므로 중복 영향 X.
    """
    agent_ids = [aid for aid in list(ws_broker._by_agent.keys()) if ws_broker._by_agent.get(aid)]
    if not agent_ids:
        return 0
    db = SessionLocal()
    try:
        repo = AgentRepository(db)
        touched = 0
        for agent_id in agent_ids:
            n = repo.touch_updated_at(agent_id)
            if n > 0:
                touched += 1
        db.commit()
        if touched > 0:
            log.info("ws-touch: touched=%d agents (online window 유지)", touched)
        return touched
    except Exception:
        # rollback 누락 시 transaction 이 abort 상태로 pool 에 반환되어 idle in transaction
        # 누적 → pool 고갈 (rc24 사고 fix).
        db.rollback()
        log.exception("ws-touch: rolled back transaction")
        raise
    finally:
        db.close()


async def _loop() -> None:
    while True:
        try:
            await _check_once()
        except Exception:  # noqa: BLE001 — 어떤 예외도 loop 멈추지 못하게
            log.exception("watcher: check failed")
        try:
            await _touch_ws_active_once()
        except Exception:  # noqa: BLE001
            log.exception("ws-touch: failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start() -> asyncio.Task[Any]:
    """main.py lifespan startup 에서 호출. 반환 task 는 shutdown 시 cancel."""
    task = asyncio.create_task(_loop(), name="agent-status-watcher")
    log.info("agent watcher started — threshold=%ds interval=%ds", STALE_THRESHOLD_SECONDS, CHECK_INTERVAL_SECONDS)
    return task
