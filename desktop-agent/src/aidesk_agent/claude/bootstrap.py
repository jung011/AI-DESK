"""신규 에이전트 부트스트랩 — 사용자가 터미널을 안 열어도 즉시 통신 가능하게.

세 가지를 처리:
  1) {workspaceDir}/.claude/settings.local.json 에 aidesk-channel MCP 권한 미리 부여
     → claude 시작 시 "Always allow" 프롬프트 자체가 안 뜸.
  2) `tmux new-session -d` 로 백그라운드 세션 시작 + claude 띄움
     → TmuxLastMileAdapter 의 last-mile delivery 가 바로 도달 가능.
  3) 백엔드 설정의 `bootstrap_prompt` 텍스트를 claude 가 입력 준비된 시점에 send-keys 로 주입
     → 모든 신규 AI 가 공통 작업 규칙 문서 등을 자동 학습.

Helper 가 호스트 사용자 권한으로 도니까 ~/.claude/* 및 사용자 워크스페이스에 자유롭게 쓸 수 있다.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx

from .._shared import has_past_session

log = logging.getLogger(__name__)

# Helper → 백엔드 호출 시 사용. reporter 와 같은 기본값.
_DEFAULT_BACKEND_URL = "http://localhost:30081"
# claude 가 첫 프롬프트를 그릴 때까지의 *초기* 대기 — 너무 짧으면 send-keys 가 이전 출력에 묻힘.
# cold start (인증 / 모델 로딩) 가 길어지는 케이스를 위해 _MAX_WAIT_SEC 안에서 polling 으로 재시도.
_BOOTSTRAP_PROMPT_DELAY_SEC = 2.5
_BOOTSTRAP_PROMPT_MAX_WAIT_SEC = 30.0
_BOOTSTRAP_PROMPT_RETRY_INTERVAL_SEC = 1.5

# Claude Code 가 워크스페이스 단위 trust 결정을 저장하는 글로벌 파일.
# projects[workspace_path] 객체에 hasTrustDialogAccepted=true 를 박아두면
# "trust this folder?" 첫 진입 프롬프트가 안 뜬다.
_CLAUDE_JSON_PATH = Path.home() / ".claude.json"

# 신규 AI 가 즉시 쓸 수 있게 하는 최소 권한 집합.
# - aidesk-channel: 사내 AI 간 협업 (내부) — 모든 AI 가 공유
# kaflix-* (사내 동료 외부 PC 통신) 는 (me) 전용 정책이라 의도적으로 포함 X.
# (me) 워크스페이스에는 scope_workspace 가 호출되어 추가 권한이 박힘.
# 사용자가 추가로 도구 (Bash, Read 등) 를 쓰려면 그때 "Always allow" 로 누적된다.
DEFAULT_ALLOW = (
    "mcp__aidesk-channel__list_agents",
    "mcp__aidesk-channel__send_to",
    "mcp__aidesk-channel__reply",
    "mcp__aidesk-channel__check_inbox",
)


def _write_default_permissions(workspace_dir: str) -> tuple[bool, int]:
    """워크스페이스의 .claude/settings.local.json 에 DEFAULT_ALLOW 를 멱등하게 주입.

    Returns (ok, added_count). 기존 파일이 있어도 우리 키만 추가하고 사용자가 누적한
    다른 도구 권한은 보존한다.
    """
    ws = Path(workspace_dir).expanduser()
    try:
        ws.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("bootstrap: workspace mkdir failed ws=%s err=%s", workspace_dir, e)
        return False, 0

    settings_path = ws / ".claude" / "settings.local.json"
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("bootstrap: .claude mkdir failed ws=%s err=%s", workspace_dir, e)
        return False, 0

    data: dict = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError) as e:
            log.warning("bootstrap: settings read failed (will overwrite) path=%s err=%s",
                        settings_path, e)
            data = {}

    if not isinstance(data, dict):
        data = {}
    perms = data.setdefault("permissions", {})
    if not isinstance(perms, dict):
        perms = data["permissions"] = {}
    allow = perms.setdefault("allow", [])
    if not isinstance(allow, list):
        allow = perms["allow"] = []

    added = 0
    for tool in DEFAULT_ALLOW:
        if tool not in allow:
            allow.append(tool)
            added += 1

    if added > 0:
        try:
            settings_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            log.warning("bootstrap: settings write failed path=%s err=%s", settings_path, e)
            return False, 0

    log.info("bootstrap: permissions ws=%s added=%d total=%d", workspace_dir, added, len(allow))
    return True, added


def _mark_folder_trusted(workspace_dir: str) -> bool:
    """`~/.claude.json` 의 projects[workspaceDir] 에 hasTrustDialogAccepted=true 를 박는다.

    이 파일은 모든 워크스페이스의 상태가 누적되어 있으므로 atomic read-modify-write 로
    처리. 같은 파일에 동시 접근이 있어도 우리 키만 안전하게 교체된다.
    """
    if not _CLAUDE_JSON_PATH.exists():
        # claude 가 한 번도 안 떴으면 파일 자체가 없음 — 새로 만들기.
        try:
            _CLAUDE_JSON_PATH.write_text("{}\n", encoding="utf-8")
        except OSError as e:
            log.warning("bootstrap: ~/.claude.json create failed err=%s", e)
            return False

    try:
        raw = _CLAUDE_JSON_PATH.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError) as e:
        log.warning("bootstrap: ~/.claude.json read failed err=%s", e)
        return False

    if not isinstance(data, dict):
        data = {}
    projects = data.setdefault("projects", {})
    if not isinstance(projects, dict):
        projects = data["projects"] = {}

    entry = projects.setdefault(workspace_dir, {})
    if not isinstance(entry, dict):
        entry = projects[workspace_dir] = {}

    # 기존 키는 보존, trust 관련 3개만 명시.
    entry["hasTrustDialogAccepted"] = True
    # CLAUDE.md 가 외부 include 를 가지고 있어도 경고 안 띄움 — 신규 AI 부팅 streamline.
    entry.setdefault("hasClaudeMdExternalIncludesApproved", True)
    entry.setdefault("hasClaudeMdExternalIncludesWarningShown", True)

    # atomic write — 큰 누적 파일이라 중간에 깨지면 다른 워크스페이스도 영향.
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".claude.json.", dir=str(_CLAUDE_JSON_PATH.parent),
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, _CLAUDE_JSON_PATH)
    except OSError as e:
        log.warning("bootstrap: ~/.claude.json write failed err=%s", e)
        return False

    log.info("bootstrap: trust marker set ws=%s", workspace_dir)
    return True


def _start_tmux_detached(tmux_session: str, workspace_dir: str) -> bool:
    """tmux 세션을 detached 로 띄우고 안에서 claude 를 실행. 이미 있으면 그대로 둠."""
    # 이미 있으면 그대로 (idempotent — 같은 AI 재생성 시 무동작)
    check = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session],
        capture_output=True,
    )
    if check.returncode == 0:
        log.info("bootstrap: tmux already exists session=%s — skipping start", tmux_session)
        return True

    # 신규 AI 라도 사용자가 같은 워크스페이스로 재생성하는 케이스가 있을 수 있어 jsonl 체크.
    claude_cmd = "claude -c" if has_past_session(workspace_dir) else "claude"

    # tmux new-session -d  → detached (사용자 화면에 안 뜸)
    # -A 와 함께 쓰면 안 됨 (-A 는 attach 의도) — -d 만 쓰면 새로 만들고 안 붙음
    try:
        subprocess.run(
            [
                "tmux", "new-session", "-d", "-s", tmux_session,
                "-c", workspace_dir,
                claude_cmd,
            ],
            check=True,
            capture_output=True,
        )
        log.info("bootstrap: tmux started detached ws=%s session=%s cmd=%s",
                 workspace_dir, tmux_session, claude_cmd)
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", "replace") if e.stderr else ""
        log.warning("bootstrap: tmux start failed session=%s err=%s", tmux_session, stderr)
        return False


def _fetch_workrole_file() -> str:
    """백엔드 설정의 workrole_file 경로 조회. 실패/미설정이면 빈 문자열.

    이 fetch 는 인증 없이 호출돼 backend 가 401 로 막는다 (= 정상 fallback 흐름).
    실제 workrole 주입은 frontend 가 bootstrap body 에 path 동봉해서 처리.
    """
    backend_url = (
        os.environ.get("AIDESK_HUB_URL")
        or os.environ.get("AIDESK_BACKEND_URL")
        or _DEFAULT_BACKEND_URL
    ).rstrip("/")
    try:
        resp = httpx.get(f"{backend_url}/api/settings/workrole-file", timeout=3.0)
        resp.raise_for_status()
        body = resp.json()
        if body.get("result") == 0:
            data = body.get("data") or {}
            path = data.get("path")
            if isinstance(path, str):
                return path
    except (httpx.HTTPError, ValueError) as e:
        log.warning("workrole_file fetch failed: %s", e)
    return ""


def _build_identity_prompt(agent_name: str) -> str:
    """에이전트 자기 정체 인지 — claude 가 signed-in user (사용자 본인) 와 자기 인스턴스를
    혼동하지 않도록 매 부트스트랩 시 명시적으로 이름을 알린다. workrole_file 미설정이어도
    이건 항상 주입된다.
    """
    return (
        f"당신은 '{agent_name}' 라는 이름의 AI 인스턴스입니다. "
        f"다른 AI 와의 모든 통신에서 본인을 '{agent_name}' 로 소개하고, "
        f"메시지에 응답할 때 사용자 (계정 소유자) 의 정체와 혼동하지 마세요."
    )


def _build_workrole_prompt(workrole_file: str) -> str:
    """workrole_file 경로를 받아 claude 에 주입할 프롬프트 문장 생성."""
    return (
        f"먼저 {workrole_file} 를 읽고 거기 안내된 모든 작업 규칙 문서들을 순서대로 숙지하세요. "
        "숙지가 끝나면 그 규칙을 따라 이후 들어오는 작업을 처리해 주세요."
    )


def _send_keys_after_delay(tmux_session: str, prompt: str) -> None:
    """claude 가 입력 받을 준비될 때까지 잠시 기다린 뒤 send-keys 로 텍스트 + Enter 주입.

    `-l` literal 모드 + 별도 Enter 분리는 paste-detect 가 Enter 를 흡수하지 않게 하기 위함.

    cold start (claude 첫 실행, 인증/모델 로딩) 가 _BOOTSTRAP_PROMPT_DELAY_SEC 보다 오래
    걸리면 send-keys 가 너무 일찍 실행돼 exit 1 또는 출력에 묻힘 → 무한 WS 재연결로 이어짐.
    그래서 *세션 alive 확인 + send-keys 재시도* 패턴으로 _MAX_WAIT_SEC 안에서 polling.
    """
    time.sleep(_BOOTSTRAP_PROMPT_DELAY_SEC)
    deadline = time.monotonic() + _BOOTSTRAP_PROMPT_MAX_WAIT_SEC
    last_err = ""
    while time.monotonic() < deadline:
        # 1) tmux 세션 alive 확인 — claude 가 죽었거나 세션 종료된 상태면 send-keys 가 exit 1
        check = subprocess.run(
            ["tmux", "has-session", "-t", tmux_session],
            capture_output=True,
        )
        if check.returncode != 0:
            last_err = "session not found yet"
            time.sleep(_BOOTSTRAP_PROMPT_RETRY_INTERVAL_SEC)
            continue
        # 2) send-keys 시도
        try:
            subprocess.run(
                ["tmux", "send-keys", "-l", "-t", tmux_session, prompt],
                check=True, capture_output=True,
            )
            time.sleep(0.2)
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_session, "Enter"],
                check=True, capture_output=True,
            )
            log.info("bootstrap: prompt injected session=%s chars=%d", tmux_session, len(prompt))
            return
        except subprocess.CalledProcessError as e:
            last_err = f"rc={e.returncode} stderr={(e.stderr or b'').decode('utf-8', 'replace').strip()}"
            log.info("bootstrap: prompt inject pending session=%s (%s) — retrying", tmux_session, last_err)
            time.sleep(_BOOTSTRAP_PROMPT_RETRY_INTERVAL_SEC)
        except OSError as e:
            last_err = str(e)
            time.sleep(_BOOTSTRAP_PROMPT_RETRY_INTERVAL_SEC)
    log.warning(
        "bootstrap: prompt inject gave up session=%s after %.0fs (last err: %s)",
        tmux_session, _BOOTSTRAP_PROMPT_MAX_WAIT_SEC, last_err,
    )


def bootstrap_agent(
    workspace_dir: str,
    tmux_session: str,
    agent_name: str = "",
    workrole_file: str = "",
) -> dict:
    """엔드포인트 본체. trust + 권한 + tmux + 프롬프트 주입 모두 시도하고 결과 dict 반환.

    순서가 중요: trust 마커가 tmux 시작 전에 박혀야 claude 첫 부팅 때 프롬프트가 안 뜬다.
    프롬프트 주입은 tmux 가 성공적으로 시작된 경우에만, 백그라운드 스레드에서 비동기로 수행 —
    호출자(HTTP 핸들러) 가 즉시 응답할 수 있게.

    agent_name 이 주어지면 identity prompt (자기 이름 인지) 를 항상 주입하고,
    workrole_file 이 설정되어 있으면 그 안내문을 뒤에 합쳐서 한 번에 보낸다.

    workrole_file 인자는 frontend 가 인증 cookie 로 미리 조회한 값. 없으면 helper 가
    비인증으로 backend 직접 호출하지만 그 endpoint 가 인증 가드 안에 있어 보통 빈 응답.
    """
    trust_ok = _mark_folder_trusted(workspace_dir)
    perms_ok, perms_added = _write_default_permissions(workspace_dir)
    tmux_ok = _start_tmux_detached(tmux_session, workspace_dir)
    prompt_scheduled = False
    if tmux_ok:
        parts: list[str] = []
        if agent_name and agent_name.strip():
            parts.append(_build_identity_prompt(agent_name.strip()))
        # 인자로 받은 path 가 있으면 그걸 우선 — frontend 가 인증해서 가져온 값.
        # 없으면 옛 helper-직접-fetch fallback (single-mac 환경에서만 동작).
        effective_workrole = workrole_file.strip() if workrole_file else _fetch_workrole_file().strip()
        if effective_workrole:
            parts.append(_build_workrole_prompt(effective_workrole))
        if parts:
            prompt = "\n\n".join(parts)
            threading.Thread(
                target=_send_keys_after_delay,
                args=(tmux_session, prompt),
                daemon=True,
            ).start()
            prompt_scheduled = True
    return {
        "trustMarked": trust_ok,
        "permissionsWritten": perms_ok,
        "permissionsAdded": perms_added,
        "tmuxStarted": tmux_ok,
        "promptScheduled": prompt_scheduled,
    }
