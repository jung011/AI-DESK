"""account_sn → helper LAN IP in-memory store.

옵션 B MVP — 모바일 frontend 가 *같은 wifi 안* 의 사용자 mac helper 한테 직접 접근
박을 수 있도록 backend 가 user-별 helper LAN IP 박은 캐시.

흐름:
1. helper reporter 의 /api/desktop/local-info payload 안 lan_ip 박혀있음 (helper 0.8.x)
2. backend apply_local_info — matched agent 의 account_sn 추출 → store[account_sn] = lan_ip
3. mobile frontend 의 /api/helper/lan-ip 호출 — auth 박힌 user 의 account_sn 으로 lookup

in-memory only — pod restart 시 분실. 해 helper reporter 30s cycle 안에 자동 복구.
multi-pod 환경에서는 redis 같은 외부 store 필요 ([[option-c-ws-proxy]] 와 같은 future).
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)


class LanIpStore:
    """thread-safe in-memory account_sn → (lan_ip, last_seen_epoch)."""

    def __init__(self, ttl_seconds: float = 180.0) -> None:
        self._lock = threading.Lock()
        self._store: dict[int, tuple[str, float]] = {}
        self._ttl = ttl_seconds

    def put(self, account_sn: int, lan_ip: str) -> None:
        if not lan_ip:
            return
        with self._lock:
            self._store[account_sn] = (lan_ip, time.time())

    def get(self, account_sn: int) -> str | None:
        with self._lock:
            entry = self._store.get(account_sn)
            if entry is None:
                return None
            lan_ip, ts = entry
            # TTL = 3분. helper reporter 30s cycle 박혀있어 정상 helper 면 항상 fresh.
            # 3분 넘은 entry = helper 죽음 / 분실 — stale lan_ip 반환 안 박음.
            if time.time() - ts > self._ttl:
                self._store.pop(account_sn, None)
                return None
            return lan_ip


# 모듈 단위 singleton
store = LanIpStore()
