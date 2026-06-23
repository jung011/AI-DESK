"""리소스 정리 — 옛 mcp daemon kill + 시스템 status 모니터링.

agent 호스팅 누적 (옛 bun aidesk-channel daemon 잔재, kernel state 누적 등) 으로
인한 통신 사고 예방용. 사용자가 대시보드에서 클릭 → 즉시 cleanup.

진짜 *kernel state* (pf table / NAT / TIME_WAIT) reset 은 mac restart 만 답.
이 모듈은 *process 잔재* 와 *cache flush* 까지만 cover. uptime 권고는 별도.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time

log = logging.getLogger(__name__)


# 옛 daemon 검출 패턴 — bun standalone binary (~/.aidesk/aidesk-channel) 또는
# node 로 실행된 옛 server.js 둘 다 잡는다.
_STALE_PROCESS_PATTERNS = (
    "aidesk-channel",  # bun standalone binary path 또는 인자 매칭
)


def _list_stale_processes() -> list[dict]:
    """현재 살아있는 aidesk-channel daemon 들. 자기 자신 (helper) 은 제외."""
    own_pid = os.getpid()
    try:
        out = subprocess.check_output(
            ["ps", "-axo", "pid=,etime=,command="],
            text=True,
            timeout=5.0,
        )
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("cleanup: ps 실행 실패: %s", e)
        return []

    result: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid_str, etime, command = parts
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == own_pid:
            continue
        # *명령어 안에* 패턴 포함 시 매칭. helper 자체 명령엔 패턴 없음.
        if not any(pat in command for pat in _STALE_PROCESS_PATTERNS):
            continue
        result.append({"pid": pid, "etime": etime, "command": command[:120]})
    return result


def kill_stale_daemons(dry_run: bool = False) -> dict:
    """옛 bun mcp daemon 일괄 kill. helper 자신 / claude code 자식 daemon 도 포함될 수 있음.

    *주의* — 사용자가 현재 작업 중인 claude code 의 자식 daemon 도 같이 종료될 수
    있다. 정상 path 에선 claude code 가 다시 spawn 해서 복구. UI 에선 confirm
    modal 로 사전 안내 필수.

    dry_run=True 면 kill 안 하고 후보 pid 만 반환 — 검증 / 미리보기 용.
    """
    candidates = _list_stale_processes()
    if dry_run:
        return {
            "killedPids": [],
            "failed": [],
            "totalFound": len(candidates),
            "dryRun": True,
            "candidates": [p["pid"] for p in candidates],
        }
    killed: list[int] = []
    failed: list[dict] = []
    for proc in candidates:
        pid = proc["pid"]
        try:
            os.kill(pid, 15)  # SIGTERM
            killed.append(pid)
        except (ProcessLookupError, PermissionError) as e:
            failed.append({"pid": pid, "reason": str(e)})

    # 짧게 기다린 후 살아있으면 SIGKILL — 좀비 daemon 강제 정리.
    if killed:
        time.sleep(0.5)
        remaining = {p["pid"] for p in _list_stale_processes()}
        for pid in list(killed):
            if pid in remaining:
                try:
                    os.kill(pid, 9)  # SIGKILL
                except (ProcessLookupError, PermissionError):
                    pass

    log.info("cleanup: killed=%d failed=%d", len(killed), len(failed))
    return {"killedPids": killed, "failed": failed, "totalFound": len(candidates)}


def _get_uptime_seconds() -> float | None:
    """macOS: sysctl kern.boottime 으로 uptime. 다른 OS 면 None."""
    try:
        out = subprocess.check_output(
            ["sysctl", "-n", "kern.boottime"], text=True, timeout=2.0
        )
        # 출력 예: "{ sec = 1718000000, usec = 0 } Mon Jun 10 09:13:20 2026"
        # sec = 다음 숫자 추출
        m = re.search(r"sec\s*=\s*(\d+)", out)
        if not m:
            return None
        boottime = int(m.group(1))
        return max(0.0, time.time() - boottime)
    except (subprocess.SubprocessError, OSError):
        return None


def get_system_status() -> dict:
    """대시보드 banner 용 — uptime + 옛 daemon 갯수 + 권고.

    *룰* — uptime 14일 초과 + agent 4개 이상 호스팅이면 mac restart 권고.
    *완전 한계* — kernel state 누적은 어떤 cleanup 으로도 reset 불가. restart 만 답.
    """
    uptime_sec = _get_uptime_seconds()
    uptime_days = (uptime_sec / 86400.0) if uptime_sec is not None else None
    stale = _list_stale_processes()
    stale_count = len(stale)

    # restart 권고 = uptime > 14일 + stale daemon 3개 이상
    restart_recommended = (
        uptime_days is not None
        and uptime_days > 14.0
        and stale_count >= 3
    )

    return {
        "uptimeSeconds": uptime_sec,
        "uptimeDays": uptime_days,
        "staleDaemonCount": stale_count,
        "staleDaemons": stale[:10],  # UI 표시용 — 너무 많으면 상위 10개만
        "restartRecommended": restart_recommended,
    }


def flush_dns_cache() -> dict:
    """dscacheutil + mDNSResponder flush. sudo 권한 필요 — 실패하면 ok=false 반환.

    사용자가 sudoers 등록 안 한 환경에선 무효. UI 에선 'optional' 로 표시.
    """
    cmds = [
        ["dscacheutil", "-flushcache"],
        ["killall", "-HUP", "mDNSResponder"],
    ]
    results = []
    for cmd in cmds:
        try:
            r = subprocess.run(
                ["sudo", "-n"] + cmd,  # -n = no password prompt
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            results.append({"cmd": " ".join(cmd), "ok": r.returncode == 0, "stderr": r.stderr.strip()[:120]})
        except (subprocess.SubprocessError, OSError, FileNotFoundError) as e:
            results.append({"cmd": " ".join(cmd), "ok": False, "stderr": str(e)[:120]})
    return {"results": results, "ok": all(r["ok"] for r in results)}
