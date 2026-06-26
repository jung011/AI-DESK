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


# 옛 daemon 검출 패턴 — *aidesk-channel binary 의 정확한 path* 만. claude TUI 의
# cmdline arg (예: `--channels server:aidesk-channel`) 나 wrapper zsh 의 env
# (`AIDESK_AGENT_ID=...`) 같은 *동일 단어 포함 line* 은 제외.
_STALE_PROCESS_PATTERNS = (
    "/aidesk-channel/bin/aidesk-channel",  # mcp daemon binary path (prod + dev 둘 다 covered)
)


def _list_stale_processes() -> list[dict]:
    """진짜 옛 잔재 (orphan) mcp daemon 들. *현재 active agent 의 정상 mcp daemon* 은 제외.

    조건:
    1. command 가 mcp binary path 정확 매칭 (`/aidesk-channel/bin/aidesk-channel`)
    2. PPID=1 (parent 가 launchd 로 reparent 됨 — orphan). 정상 daemon = PPID=claude TUI 의 pid.
       이게 *진짜 옛 잔재* 의 신호 — parent claude 가 죽었는데 mcp 만 살아있음.

    self (helper) 는 제외.
    """
    own_pid = os.getpid()
    try:
        # ppid 도 같이 — orphan 검사용
        out = subprocess.check_output(
            ["ps", "-axo", "pid=,ppid=,etime=,command="],
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
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid_str, ppid_str, etime, command = parts
        try:
            pid = int(pid_str)
            ppid = int(ppid_str)
        except ValueError:
            continue
        if pid == own_pid:
            continue
        # 1) command 의 *binary path 정확 매칭*
        if not any(pat in command for pat in _STALE_PROCESS_PATTERNS):
            continue
        # 2) PPID=1 (orphan) 만 — 정상 daemon (PPID=claude TUI) 제외
        if ppid != 1:
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
    """macOS uptime — sysctl kern.boottime. PyInstaller bundle 환경에선 PATH 가 제한적이라
    절대경로 fallback 시도. 출력 형식도 macOS 버전마다 달라 정규식 2-단계.

    출력 가능 형식:
      - `{ sec = 1718000000, usec = 0 } Mon Jun 10 09:13:20 2026`  (BSD 전통)
      - `{1718000000, 0} Mon Jun 10 09:13:20 2026`  (최근 macOS)
      - `1718000000` (raw sec only)
    """
    for sysctl_bin in ("/usr/sbin/sysctl", "/sbin/sysctl", "sysctl"):
        try:
            out = subprocess.check_output(
                [sysctl_bin, "-n", "kern.boottime"],
                text=True, timeout=2.0, stderr=subprocess.PIPE,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            continue
        # 1차 — `sec = <digits>` 패턴
        m = re.search(r"sec\s*=\s*(\d+)", out)
        if m:
            return max(0.0, time.time() - int(m.group(1)))
        # 2차 — `{<digits>, <digits>}` 또는 raw `<digits>` 패턴
        m = re.search(r"\{?\s*(\d{9,})\s*[,}]?", out)
        if m:
            return max(0.0, time.time() - int(m.group(1)))
        log.warning("cleanup: kern.boottime 출력 파싱 실패: %r", out[:200])
        return None
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
