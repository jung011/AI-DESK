"""신규 에이전트 부트스트랩 + 외부 터미널 열기 시점의 claude 시작.

정책: 신규 AI 생성 시점엔 *준비 작업만* 수행. 실제 claude 실행은 사용자가
*외부 터미널 열기* 를 누르고 모드 (클로드 / 텔레그램 / 사용자 지정 옵션) 를 선택했을 때
시작한다. 외부 터미널 열기 전엔 claude 가 안 떠 있어서 메시지 수신 불가 (옵션 2 분기로
즉시 failed) — 의도된 동작.

두 진입점:
  bootstrap_agent()        — agent 생성 직후 호출. trust + permissions 만.
  start_claude_with_mode() — 외부 터미널 열기 시점 호출. mode 별 claude_cmd 구성 →
                             tmux+claude 시작 → 첫 부팅이면 identity/workrole send-keys 주입.

mode:
  - 'claude'   (default) : `claude` (첫 실행) / `claude -c` (재실행)
  - 'telegram'           : `claude --channels plugin:telegram@claude-plugins-official` (+`-c`)
  - 'custom'             : `claude <custom_opts>` (+`-c`)

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


def _resolve_user_path() -> str | None:
    """사용자의 interactive login zsh 에서 실제 PATH 한 번 조회.

    helper 의 launchd 환경 PATH 는 plist 에 hardcoded — 사용자가 `.zprofile` / `.zshrc` 에서
    추가한 경로 (예: `~/.bun/bin`, `~/.cargo/bin`, nvm 의 node 경로) 는 누락된다. claude code
    의 MCP plugin 이 거기 있는 도구 (예: `bun run ...`) 를 spawn 하면 *command not found* 로
    실패. 이 함수가 사용자 zsh 의 실제 PATH 를 가져와 tmux session env 로 주입할 수 있게 한다.

    실패 시 None — 호출자가 helper 의 기본 PATH 그대로 사용 (회귀 없음).
    """
    try:
        result = subprocess.run(
            ["/bin/zsh", "-l", "-i", "-c", "echo -n $PATH"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            log.warning("bootstrap: user PATH resolve failed rc=%d stderr=%s",
                        result.returncode, (result.stderr or "").strip())
            return None
        path = (result.stdout or "").strip()
        return path or None
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning("bootstrap: user PATH resolve exception: %s", e)
        return None


def _build_claude_cmd(workspace_dir: str, mode: str, custom_opts: str = "") -> str:
    """mode 별 tmux 안에서 실행할 claude 명령 구성.

    - mode='claude'   : `claude` (또는 재실행이면 `claude -c`)
    - mode='telegram' : `claude --channels plugin:telegram@claude-plugins-official` (+`-c`)
    - mode='custom'   : `claude <custom_opts>` (+`-c`)

    `-c` (continue) 는 .claude/projects/<ws>/ 안에 이전 jsonl 대화가 있으면 자동 추가 —
    사용자가 exit/Ctrl+C 후 다시 모드 선택해서 띄우는 시나리오에서 컨텍스트를 살리기 위함.
    """
    extra = ""
    if mode == "telegram":
        extra = "--channels plugin:telegram@claude-plugins-official"
    elif mode == "custom":
        extra = (custom_opts or "").strip()
    cmd = "claude"
    if extra:
        cmd = f"{cmd} {extra}"
    if has_past_session(workspace_dir):
        cmd = f"{cmd} -c"
    return cmd


def _start_tmux_detached(tmux_session: str, workspace_dir: str, claude_cmd: str) -> bool:
    """tmux 세션을 detached 로 띄우고 안에서 주어진 claude_cmd 를 실행. 이미 있으면 그대로 둠.

    claude_cmd 는 호출자가 _build_claude_cmd 로 구성해서 넘긴다 — mode (클로드/텔레그램/custom) 결정은
    상위에서 한다.
    """
    # 이미 있으면 그대로 (idempotent — 같은 AI 재생성 시 무동작)
    check = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session],
        capture_output=True,
    )
    if check.returncode == 0:
        log.info("bootstrap: tmux already exists session=%s — skipping start", tmux_session)
        return True

    # tmux new-session -d  → detached (사용자 화면에 안 뜸)
    # -A 와 함께 쓰면 안 됨 (-A 는 attach 의도) — -d 만 쓰면 새로 만들고 안 붙음
    # -e PATH=... → 사용자 zsh 의 실제 PATH 를 새 session env 에 주입 (있을 때만).
    # 그래야 claude code 가 spawn 하는 MCP plugin (예: telegram 의 `bun run ...`) 이
    # 사용자가 `~/.bun/bin` 등에 깐 도구를 찾을 수 있다. plist 의 hardcoded PATH 만으론
    # 사용자별 dev tool 위치를 못 잡음.
    user_path = _resolve_user_path()
    cmd_list = ["tmux", "new-session", "-d", "-s", tmux_session, "-c", workspace_dir]
    if user_path:
        cmd_list.extend(["-e", f"PATH={user_path}"])
    cmd_list.append(claude_cmd)
    try:
        subprocess.run(cmd_list, check=True, capture_output=True)
        log.info("bootstrap: tmux started detached ws=%s session=%s cmd=%s user_path=%s",
                 workspace_dir, tmux_session, claude_cmd, "yes" if user_path else "no")
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
    """신규 AI 생성 직후 호출 — 준비 작업만 수행 (claude/tmux 시작 안 함).

    옛 정책: 여기서 tmux + claude 자동 시작 + 워크롤/identity 자동 주입.
    새 정책: 사용자가 외부 터미널 열기 → 모드 선택 시점에 start_claude_with_mode 가 처리.

    이 함수는 trust + permissions 만 보장 — claude 가 처음 뜰 때 "trust this folder?" 와
    "Always allow this tool?" 프롬프트가 안 뜨도록 미리 ~/.claude.json 과
    {ws}/.claude/settings.local.json 에 마커/권한을 박아둔다.

    agent_name / workrole_file 인자는 BC 위해 받지만 사용 안 함 — 외부 터미널 열기 시점에
    start_claude_with_mode 에 다시 전달된다.
    """
    trust_ok = _mark_folder_trusted(workspace_dir)
    perms_ok, perms_added = _write_default_permissions(workspace_dir)
    return {
        "trustMarked": trust_ok,
        "permissionsWritten": perms_ok,
        "permissionsAdded": perms_added,
        "tmuxStarted": False,   # 새 정책 — 외부 터미널 열기 시점에 시작
        "promptScheduled": False,
    }


def start_claude_with_mode(
    workspace_dir: str,
    tmux_session: str,
    mode: str = "claude",
    custom_opts: str = "",
    agent_name: str = "",
    workrole_file: str = "",
) -> dict:
    """외부 터미널 열기 시점에 호출 — mode 별 claude 시작 + (첫 부팅이면) identity/workrole 주입.

    이미 동일 tmux 세션이 살아있으면 _start_tmux_detached 가 skip 하고 True 반환 (idempotent) —
    이 경우 mode 는 무시되고 기존 claude 가 그대로 유지된다. 모드 변경하려면 사용자가
    exit/Ctrl+C 로 종료해서 tmux 세션을 죽인 뒤 다시 외부 터미널 열기에서 모드를 고르는 흐름.

    mode:
      - 'claude'   (default) — 그냥 claude
      - 'telegram'           — `claude --channels plugin:telegram@claude-plugins-official`
      - 'custom'             — `claude <custom_opts>`
    이전 jsonl 대화가 있으면 모든 모드에 자동으로 `-c` 가 추가된다 (컨텍스트 살리기).

    identity/workrole 은 *첫 부팅* (이전 jsonl 없는 상태) 에만 주입 — `-c` 로 재실행할 땐 이미
    이전 컨텍스트에 들어가 있으므로 중복 X.
    """
    is_first_boot = not has_past_session(workspace_dir)
    claude_cmd = _build_claude_cmd(workspace_dir, mode, custom_opts)
    tmux_ok = _start_tmux_detached(tmux_session, workspace_dir, claude_cmd)
    prompt_scheduled = False
    if tmux_ok and is_first_boot:
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
        "claudeCmd": claude_cmd,
        "mode": mode,
        "tmuxStarted": tmux_ok,
        "promptScheduled": prompt_scheduled,
        "isFirstBoot": is_first_boot,
    }
