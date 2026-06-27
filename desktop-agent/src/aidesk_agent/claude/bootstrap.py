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
import sys
import shlex
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
# Channels confirmation dialog 가 *시작 시 1회* 뜸 — confirmation Enter 후 prompt
# 영역 ready 까지 ~4-6s. delay 8s 면 안전. _BOOTSTRAP_PROMPT_MAX_WAIT_SEC 안의 retry
# 로 cold start 더 오래 걸려도 잡힘.
_BOOTSTRAP_PROMPT_DELAY_SEC = 8.0
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


def _resolve_backend_url() -> str:
    """mcp daemon (aidesk-channel bun) 의 AIDESK_API_URL = helper proxy 경유.

    [[feedback-mcp-bun-external-connect-block]] — bun runtime 의 외부 IP socket
    allocation 이 macOS kernel state 누적으로 차단되는 사고 영구 fix.
    mcp daemon 은 localhost helper 에만 connect → helper(python aiohttp) 가 backend 로
    forward. agent 다수 호스팅 mac 의 kernel state 누적 layer 무관.
    """
    helper_port = os.environ.get("AIDESK_HELPER_PORT", "30083")
    return f"http://127.0.0.1:{helper_port}/api/proxy"


_LOCAL_MCP_NAME = "aidesk-channel"
# dev / prod 분기 — _shared.aidesk_share_dir 일원화.
# [[feedback-dev-prod-environment-separation]]
from .._shared import aidesk_share_dir as _aidesk_share_dir  # noqa: E402
_LOCAL_MCP_BIN = f"{_aidesk_share_dir()}/aidesk-channel/bin/aidesk-channel"


def _register_local_mcp(
    workspace_dir: str,
    agent_id: str,
    api_url: str | None = None,
    helper_url: str | None = None,
) -> bool:
    """`~/.claude.json` 의 `projects[ws].mcpServers["aidesk-channel"]` 에 local mcp 등록.

    - AIDESK_AGENT_ID env 명시 → mcp ensureAgentId 가 cwd fallback 없이 caller 식별
    - 글로벌 mcpServers["aidesk-channel"] 이 있으면 자동 제거 (마이그레이션)
    - api_url 인자 = workspace-별 *backend override* (dev 전용). None 면 _resolve_backend_url().
    - helper_url 인자 = mcp 가 local-info 조회할 helper URL (dev 전용 — 30084 등).
      None 면 mcp default (localhost:30083 prod helper). mcp 가 helper 의 currentBackendUrl
      로 *override* 하기 때문에 dev 에서는 dev helper URL 명시 필수.

    Phase 6 의 글로벌 → workspace local 패턴. multi-user 격리 + caller 명확화.
    """
    if not agent_id or not workspace_dir:
        return False
    if not _CLAUDE_JSON_PATH.exists():
        try:
            _CLAUDE_JSON_PATH.write_text("{}\n", encoding="utf-8")
        except OSError as e:
            log.warning("bootstrap: ~/.claude.json create failed err=%s", e)
            return False
    try:
        data = json.loads(_CLAUDE_JSON_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError) as e:
        log.warning("bootstrap: ~/.claude.json read failed (will overwrite) err=%s", e)
        data = {}
    if not isinstance(data, dict):
        data = {}

    # legacy 글로벌 entry 제거 — 옛 패턴 흔적.
    legacy_servers = data.get("mcpServers")
    if isinstance(legacy_servers, dict) and _LOCAL_MCP_NAME in legacy_servers:
        del legacy_servers[_LOCAL_MCP_NAME]
        log.info("bootstrap: removed legacy global mcpServers.%s", _LOCAL_MCP_NAME)

    projects = data.setdefault("projects", {})
    if not isinstance(projects, dict):
        projects = data["projects"] = {}
    proj = projects.setdefault(workspace_dir, {})
    if not isinstance(proj, dict):
        proj = projects[workspace_dir] = {}
    servers = proj.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = proj["mcpServers"] = {}

    # rc20 — aidesk-channel mcp 가 bun compile standalone binary.
    # 옛 'node' + script 패턴 → binary 직접 실행. node 의존 X + 외부 AI mcp 와 통일.
    env = {
        "AIDESK_AGENT_ID": agent_id,
        "AIDESK_API_URL": (api_url or _resolve_backend_url()),
    }
    if helper_url:
        # dev 전용 — mcp 가 prod helper (30083) 대신 dev helper (30084) 조회.
        env["AIDESK_HELPER_URL"] = helper_url
    servers[_LOCAL_MCP_NAME] = {
        "type": "stdio",
        "command": _LOCAL_MCP_BIN,
        "args": [],
        "env": env,
    }
    try:
        _CLAUDE_JSON_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("bootstrap: ~/.claude.json write failed err=%s", e)
        return False
    log.info("bootstrap: registered local mcp ws=%s agent_id=%s", workspace_dir, agent_id)
    return True


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
    """mode 별 tmux 안에서 실행할 명령 구성.

    - mode='claude'   : `claude --dangerously-load-development-channels server:aidesk-channel`
                        (Channels push-to-wake 활성 — idle 자동 wake + AI Desk 채널 inject).
                        재실행이면 `-c` 추가.
    - mode='telegram' : `claude --channels plugin:telegram@claude-plugins-official` (+`-c`)
    - mode='custom'   : 사용자 입력을 `exec zsh -ic '<입력>'` 으로 wrap — alias / shell function /
                        .zshrc 정의 env 모두 expand. 사용자가 `myclaude` 같은 alias 든
                        `claude --channels plugin:slack@... -c` 같은 옵션이든 자유 입력.

    `-c` (continue) 는 .claude/projects/<ws>/ 안에 이전 jsonl 대화가 있으면 자동 추가 —
    사용자가 exit/Ctrl+C 후 다시 모드 선택해서 띄우는 시나리오에서 컨텍스트를 살리기 위함.
    단 mode='custom' 은 사용자가 명령을 통째로 적는 모드라 `-c` 자동 추가 X (필요하면 본인이 명시).

    [[project-claude-code-agent-teams]] — default mode 에 Channels flag 박는 이유:
    Channels = idle agent push-to-wake 메커니즘. flag 없으면 mcp daemon 이 메시지
    받아도 *prompt 안 inject* 되어 사용자 input 없이는 응답 X. flag 박으면 *Channels
    (experimental) messages from server:aidesk-channel inject directly* 활성.
    confirmation dialog 가 *시작 시 1회* 뜸 — tmux 안 helper 가 1회 Enter 자동화.
    """
    if mode == "custom":
        user_cmd = (custom_opts or "").strip()
        if not user_cmd:
            # 입력 없으면 안전 fallback — 사용자가 직접 띄울 수 있게 login interactive zsh.
            user_cmd = "exec zsh -li"
        return f"exec zsh -ic {shlex.quote(user_cmd)}"
    extra = ""
    if mode == "telegram":
        extra = "--channels plugin:telegram@claude-plugins-official"
    else:
        # default mode = AI Desk Channels (push-to-wake) 활성.
        # Agent Teams 분할창 모드 flag (--teammate-mode tmux) + env 는
        # ~/.claude/settings.json 의 teammateMode=auto + CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
        # 박혀있어 *불필요 중복*. tmux session 안 = settings auto 가 자동 검출 → split-window.
        extra = "--dangerously-load-development-channels server:aidesk-channel"
    cmd = "claude"
    if extra:
        cmd = f"{cmd} {extra}"
    # 텔레그램 모드는 plugin channel 통신이라 local jsonl 저장 timing 이 다른 듯 —
    # has_past_session 가 False 반환하는 케이스가 있어 *exit 후 다시 텔레그램 모드 진입* 시
    # 대화가 안 이어지는 문제 발생. claude 는 -c 받았는데 이전 대화 없으면 새 대화로 시작
    # (graceful fallback) 하므로 텔레그램 모드는 항상 -c 추가해서 안전하게 이어가기.
    if mode == "telegram" or has_past_session(workspace_dir):
        cmd = f"{cmd} -c"
    return cmd


def _start_tmux_detached(tmux_session: str, workspace_dir: str, claude_cmd: str, mode: str = "claude") -> bool:
    """tmux 세션을 detached 로 띄우고 안에서 주어진 claude_cmd 를 실행. 이미 있으면 그대로 둠.

    claude_cmd 는 호출자가 _build_claude_cmd 로 구성해서 넘긴다 — mode (클로드/텔레그램/custom) 결정은
    상위에서 한다. mode 는 PATH= prefix 적용 여부 결정에 사용 — custom 모드는 이미 `exec zsh -ic`
    안에서 .zshrc 가 PATH 를 다시 set 하므로 prefix 가 불필요/충돌.
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
    #
    # PATH 주입 — *shell-command 자체에 prefix* 로 박는다 (`-e PATH=...` 도 같이 두지만 보조).
    # 사용자 환경에 따라 tmux server env 가 이미 baked-in (예: 사용자가 처음 tmux 를 띄운
    # iTerm 의 환경) 인 경우 `-e PATH=...` 는 *session env* 에만 들어가고 *실제 child process
    # env 에는 안 닿는다*. 그러면 claude 가 spawn 하는 MCP plugin (예: telegram 의 `bun ...`)
    # 이 `bun` 을 PATH 에서 못 찾아 `ENOENT` 로 실패.
    # → `PATH=<user-path> exec <claude_cmd>` 형태로 sh syntax 의 env-prefix 사용해서
    #   claude process 의 env.PATH 를 직접 set. 그 자식 process (bun MCP server) 도 inherit.
    user_path = _resolve_user_path()
    cmd_list = ["tmux", "new-session", "-d", "-s", tmux_session, "-c", workspace_dir]
    if user_path:
        cmd_list.extend(["-e", f"PATH={user_path}"])
    # Agent Teams env (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1) 는 ~/.claude/settings.json
    # 박혀있어 중복 — 제거. settings 의 *자동 검출* (tmux session 안) 으로 충분.
    if mode == "custom":
        # claude_cmd 가 이미 `exec zsh -ic '...'` 형태 — zsh 가 .zshrc 거치며 PATH/env 다시
        # set 하므로 sh 단계의 PATH= prefix 가 무의미하고 오히려 zsh 의 export 와 섞일 위험.
        shell_cmd = claude_cmd
    elif user_path:
        shell_cmd = f"PATH={shlex.quote(user_path)} exec {claude_cmd}"
    else:
        shell_cmd = claude_cmd
    cmd_list.append(shell_cmd)
    try:
        subprocess.run(cmd_list, check=True, capture_output=True)
        log.info("bootstrap: tmux started detached ws=%s session=%s shell_cmd=%s user_path=%s",
                 workspace_dir, tmux_session, shell_cmd, "yes" if user_path else "no")

        # Channels confirmation dialog 자동 Enter — claude --dangerously-load-development-channels
        # 시작 시 *시작 시점* 에 한 번 "I am using this for local development" 선택 dialog
        # 떴는데, headless tmux 안에선 사용자 손 없음 → Enter 자동 발사 필요.
        # 3초 후 schedule (claude 시작 + dialog 표시까지 시간 확보).
        # mode='telegram' 또는 'custom' 은 *Channels dialog 없음* — skip.
        if mode not in ("telegram", "custom") and "--dangerously-load-development-channels" in claude_cmd:
            def _send_confirm_enter() -> None:
                import time
                time.sleep(3)
                try:
                    subprocess.run(["tmux", "send-keys", "-t", tmux_session, "C-m"],
                                   capture_output=True, timeout=2)
                    log.info("bootstrap: Channels confirmation Enter sent session=%s", tmux_session)
                except (subprocess.SubprocessError, OSError) as e:
                    log.warning("bootstrap: confirmation Enter failed session=%s err=%s", tmux_session, e)
            t = threading.Thread(target=_send_confirm_enter, daemon=True)
            t.start()

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
        f"메시지에 응답할 때 사용자 (계정 소유자) 의 정체와 혼동하지 마세요. "
        f"특히 '휴먼' 이라는 이름의 agent (model='human') 은 사용자 본인 (계정 소유자) "
        f"입니다. 휴먼이 보낸 메시지 = 사용자 직접 지시 — 다른 AI 의 요청과 동등하게 "
        f"취급하지 말고, 사용자 의도에 맞게 우선 처리하세요."
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
        # 2) claude prompt 영역 ready 검사 — capture-pane 으로 *Try "..."* sample tip
        #    또는 *❯ ` (빈 prompt) 가 보여야 함. Channels confirmation dialog 단계
        #    (`I am using this for local development`) 면 prompt 영역 아님 — wait.
        try:
            cap = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", tmux_session],
                capture_output=True, text=True, timeout=2,
            )
            screen = cap.stdout or ""
            is_dialog = "I am using this for local development" in screen
            has_prompt = "for agents" in screen  # claude TUI 의 footer indicator
            if is_dialog or not has_prompt:
                last_err = "claude prompt not ready (dialog or loading)"
                time.sleep(_BOOTSTRAP_PROMPT_RETRY_INTERVAL_SEC)
                continue
        except (subprocess.TimeoutExpired, OSError):
            pass  # capture 실패 — send-keys 시도로 진행
        # 3) send-keys 시도
        try:
            subprocess.run(
                ["tmux", "send-keys", "-l", "-t", tmux_session, prompt],
                check=True, capture_output=True,
            )
            # paste-bracketed mode 안 흡수되도록 충분히 wait — 0.5s 부족 사고
            # ([[feedback-helper-send-keys-c-m-fix]] 옛 fix 도 최근 claude TUI 버전엔
            # 안 통과). 2s + Enter keysym + C-m fallback 둘 다 시도. 빈 Enter 한 번
            # 추가는 prompt submit 1회 추가 사고 없음 (이미 submit 후 prompt 비워짐).
            time.sleep(2.0)
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_session, "Enter"],
                check=True, capture_output=True,
            )
            time.sleep(0.3)
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_session, "C-m"],
                check=False, capture_output=True,
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
    agent_id: str = "",
) -> dict:
    """신규 AI 생성 직후 호출 — 준비 작업만 수행 (claude/tmux 시작 안 함).

    옛 정책: 여기서 tmux + claude 자동 시작 + 워크롤/identity 자동 주입.
    새 정책: 사용자가 외부 터미널 열기 → 모드 선택 시점에 start_claude_with_mode 가 처리.

    이 함수는 trust + permissions + local mcp 만 보장 — claude 가 처음 뜰 때 "trust this folder?" 와
    "Always allow this tool?" 프롬프트가 안 뜨도록 미리 ~/.claude.json 과
    {ws}/.claude/settings.local.json 에 마커/권한/mcp 를 박아둔다.

    agent_name / workrole_file 인자는 BC 위해 받지만 사용 안 함 — 외부 터미널 열기 시점에
    start_claude_with_mode 에 다시 전달된다.
    """
    trust_ok = _mark_folder_trusted(workspace_dir)
    perms_ok, perms_added = _write_default_permissions(workspace_dir)
    # dev env — mcp(bun) 가 default HELPER_URL=http://localhost:30083 (prod) 가 아닌
    # dev helper port 사용하도록 env 자동 박음. prod 는 default 가 일치 → 박지 않음.
    helper_url = None
    if os.environ.get("AIDESK_ENV") == "dev":
        helper_port = os.environ.get("AIDESK_HELPER_PORT", "30084")
        helper_url = f"http://127.0.0.1:{helper_port}"
    mcp_ok = _register_local_mcp(workspace_dir, agent_id, helper_url=helper_url) if agent_id else False
    return {
        "trustMarked": trust_ok,
        "permissionsWritten": perms_ok,
        "permissionsAdded": perms_added,
        "mcpRegistered": mcp_ok,
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
    agent_id: str = "",
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
    # local mcp 보장 — bootstrap_agent 가 안 호출됐거나 marker 누락 케이스 보강 (idempotent).
    if agent_id:
        _register_local_mcp(workspace_dir, agent_id)
    claude_cmd = _build_claude_cmd(workspace_dir, mode, custom_opts)
    tmux_ok = _start_tmux_detached(tmux_session, workspace_dir, claude_cmd, mode)
    prompt_scheduled = False
    # 모드 무관하게 첫 부팅이면 identity/workrole 자동 주입 — 대다수 사용자가 custom 모드에서도
    # claude 시작용 alias 를 쓰기 때문. 비-claude 명령 (htop 등) 을 의도적으로 입력한 경우엔
    # 그 명령 화면에 텍스트가 박히지만 사용자 의도 영역으로 받아들인다.
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
    # PoC v1 — tmux 시작 성공 + agent_id 가 있으면 봇 어댑터 자식 process spawn.
    bot_spawned = False
    if tmux_ok and agent_id:
        bot_spawned = ensure_bot_adapter(agent_id, tmux_session)

    return {
        "claudeCmd": claude_cmd,
        "mode": mode,
        "tmuxStarted": tmux_ok,
        "promptScheduled": prompt_scheduled,
        "isFirstBoot": is_first_boot,
        "botAdapterSpawned": bot_spawned,
    }


# agent_id → (process, tmux_session, spawn_time_monotonic) registry. helper module global.
# tmux_session 은 죽었을 때 skip set unregister 용. spawn_time 은 안정 동작 판정용 (fail_count reset).
_bot_adapter_procs: dict[str, tuple[subprocess.Popen, str, float]] = {}

# agent_id → 연속 crash 카운트. 안정 동작 (>= _BOT_ADAPTER_STABLE_SEC) 이면 reset.
_bot_adapter_fail_counts: dict[str, int] = {}

# 5분 이상 살아있으면 안정 — 다음 crash 시 fail_count 가 1 부터 시작.
_BOT_ADAPTER_STABLE_SEC = 300.0
# 최대 연속 재spawn 시도. 초과 시 fallback 만 유지 (sse_consumer 가 last-mile).
_BOT_ADAPTER_MAX_RESPAWN = 5


def ensure_bot_adapter(agent_id: str, tmux_session: str) -> bool:
    """B Phase 5 (dev 브랜치 Channels 통일 정책) — bot-adapter spawn 영구 skip.

    옛 책임 = ws 받아 tmux send-keys (last-mile). Channels inject 가 그 역할 대체
    → bot-adapter 굳이 spawn 안 함. orphan cleanup (cleanup_orphan_bot_adapters) 은
    그대로 유지 — 옛 helper 가 spawn 한 잔재 정리 책임.

    caller (server.py open_terminal_handler 등) 호환 위해 False 반환 — *spawn 안 함*
    의 의미. sse_consumer skip set 등록도 안 함 (sse_consumer 자체가 last-mile 안 함).
    """
    return False


def monitor_bot_adapters() -> int:
    """봇 어댑터 자식 process 가 살아있는지 점검 + 죽었으면 즉시 자동 재spawn.

    background task 에서 주기적으로 호출 (server.py 의 _bot_adapter_monitor_loop).
    죽은 process 가 있으면:
      1. registry 에서 제거
      2. fail_count 갱신 (안정 동작 5분+ 이었으면 1 로 reset, 아니면 +1)
      3. fail_count <= MAX_RESPAWN 이면 즉시 재spawn + skip set 다시 등록
      4. MAX_RESPAWN 초과면 fallback 만 유지 (sse_consumer 가 send-keys + ack)
         외부 AI (24/7) 환경에서 사용자 액션 없이도 자동 복구 보장.

    반환값: 정리한 죽은 process 개수.
    """
    dead = 0
    for agent_id, (proc, tmux_session, spawn_time) in list(_bot_adapter_procs.items()):
        if proc.poll() is None:
            continue
        rc = proc.returncode
        alive_sec = time.monotonic() - spawn_time
        _bot_adapter_procs.pop(agent_id, None)
        dead += 1

        # 안정 동작 5분 넘었으면 backoff reset — 외부 영향 (network blip 등) 으로 죽은 것 가정.
        if alive_sec >= _BOT_ADAPTER_STABLE_SEC:
            _bot_adapter_fail_counts.pop(agent_id, None)
        fail_count = _bot_adapter_fail_counts.get(agent_id, 0) + 1
        _bot_adapter_fail_counts[agent_id] = fail_count

        log.warning("bot-adapter: monitor detected dead agent_id=%s rc=%d tmux=%s alive=%.1fs attempt=%d",
                    agent_id, rc, tmux_session, alive_sec, fail_count)

        from ..tmux.sse_consumer import register_bot_adapter_session, unregister_bot_adapter_session

        if fail_count > _BOT_ADAPTER_MAX_RESPAWN:
            log.warning("bot-adapter: max respawn attempts (%d) reached agent_id=%s — staying on sse_consumer fallback",
                        _BOT_ADAPTER_MAX_RESPAWN, agent_id)
            unregister_bot_adapter_session(tmux_session)
            continue

        # 즉시 자동 재spawn 시도.
        new_proc = _spawn_bot_adapter(agent_id, tmux_session)
        if new_proc is None:
            log.warning("bot-adapter: auto-respawn failed agent_id=%s — fallback to sse_consumer", agent_id)
            unregister_bot_adapter_session(tmux_session)
            continue
        _bot_adapter_procs[agent_id] = (new_proc, tmux_session, time.monotonic())
        # skip set 은 ensure_bot_adapter 가 register 했던 그대로 유지하지만, 죽었다가 살아나는 경계라
        # 명시적으로 다시 register (idempotent — set.add 라 중복 무해).
        register_bot_adapter_session(tmux_session)
        log.info("bot-adapter: auto-respawned pid=%d agent_id=%s attempt=%d",
                 new_proc.pid, agent_id, fail_count)
    return dead


# 봇 어댑터 자식 stdout/stderr 를 per-agent log file 로 redirect.
# DEVNULL 이면 ack POST 결과 / ws connect 상태 확인 불가 — 디버깅 + 자가치유 monitor 의 기반.
_BOT_ADAPTER_LOG_DIR = Path.home() / "Library" / "Logs"


def _bot_adapter_log_path(agent_id: str) -> Path:
    return _BOT_ADAPTER_LOG_DIR / f"aidesk-bot-adapter-{agent_id}.log"


# helper 가 spawn 한 봇 어댑터를 식별하는 binary path 들.
# Phase 2 후 외부 AI 의 daemon 봇 어댑터는 npm install 위치라 path 가 달라 충돌 X.
_BOT_ADAPTER_HELPER_BIN_PATHS = (
    f"{_aidesk_share_dir()}/aidesk-bot-adapter/bin/aidesk-bot-adapter",
    str(Path.home() / "Documents/jsh/workspace/ai-desk/aidesk-bot-adapter/bin/aidesk-bot-adapter"),
)


def cleanup_orphan_bot_adapters() -> int:
    """이전 helper 가 spawn 한 봇 어댑터들 cleanup.

    helper 재기동 시점 (예: 새 .pkg 설치) 에 launchd 가 옛 helper 만 죽이고
    그 자식 봇 어댑터들은 살아남음 (orphan). 새 helper 의 _bot_adapter_procs 에는
    없는 process 들이 backend ws 유지 + 메시지 수신 → 사용자가 외부 터미널 클릭
    시 같은 agentId 봇 어댑터가 두 개 동시 동작 + 같은 메시지 2번 send-keys.

    helper startup 시 *helper 가 띄우는 정확한 binary path* 의 process 만 pkill.
    외부 AI 의 daemon 봇 어댑터 (npm install 위치) 와는 path 다름 → 충돌 X.

    반환값: cleanup 시도한 target path 중 매칭이 있던 개수.
    """
    killed_any = 0
    for target in _BOT_ADAPTER_HELPER_BIN_PATHS:
        try:
            # pkill -f → full command line 에서 target path substring 매칭.
            # exit code: 0 = match + killed, 1 = no match, >=2 = error.
            result = subprocess.run(["pkill", "-f", target], check=False, capture_output=True)
            if result.returncode == 0:
                killed_any += 1
                log.info("orphan bot-adapter cleanup: killed any matching target=%s", target)
        except OSError as e:
            log.warning("orphan bot-adapter cleanup: pkill failed target=%s err=%s", target, e)
    return killed_any


def _spawn_bot_adapter(agent_id: str, tmux_session: str) -> subprocess.Popen | None:
    """봇 어댑터 자식 process spawn.

    - binary: helper-pkg payload 의 `{aidesk_share_dir}/aidesk-bot-adapter/bin/aidesk-bot-adapter`
              (운영 .pkg 배포 시 = prod, dev .pkg = -dev/ 분기). 개발자 mac monorepo path fallback.
    - env: AIDESK_AGENT_ID + AIDESK_HUB_URL + AIDESK_TMUX_SESSION.
    - stdout/stderr: ~/Library/Logs/aidesk-bot-adapter-<agent_id>.log (append) — ack POST
      결과, ws connect/disconnect, tmux send-keys 결과를 self-contained 로 확인 가능.
    - detached subprocess (start_new_session=True) — helper 종료 시 자식도 함께 종료되지만
      session 분리로 tmux send-keys 와 충돌 X.
    - 실패 시 log warning + 어댑터 없이 helper sse_consumer 만으로 fallback (회귀 방지).
    """
    bin_candidates = [
        f"{_aidesk_share_dir()}/aidesk-bot-adapter/bin/aidesk-bot-adapter",
        str(Path.home() / "Documents/jsh/workspace/ai-desk/aidesk-bot-adapter/bin/aidesk-bot-adapter"),
    ]
    bin_path = next((p for p in bin_candidates if Path(p).exists()), None)
    if not bin_path:
        log.warning("bot-adapter: binary not found in %s — skip spawn (agent_id=%s)",
                    bin_candidates, agent_id)
        return None

    hub_url = os.environ.get("AIDESK_HUB_URL")
    if not hub_url:
        log.warning("bot-adapter: AIDESK_HUB_URL env missing — skip spawn (agent_id=%s)", agent_id)
        return None

    env = os.environ.copy()
    env["AIDESK_AGENT_ID"] = agent_id
    env["AIDESK_HUB_URL"] = hub_url
    env["AIDESK_TMUX_SESSION"] = tmux_session
    # B Phase 4 — bot-adapter 도 helper broker loopback 우회. helper port (dev=30084,
    # prod=30083) 의 ws://.../ws/messages-broker?agentId=... 로 connect.
    helper_port = os.environ.get("AIDESK_HELPER_PORT", "30083")
    env["AIDESK_HELPER_URL"] = f"http://127.0.0.1:{helper_port}"

    log_path = _bot_adapter_log_path(agent_id)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_path, "a", buffering=1)
    except OSError as e:
        log.warning("bot-adapter: log file open failed path=%s err=%s — using DEVNULL", log_path, e)
        log_fh = None

    try:
        proc = subprocess.Popen(
            [bin_path],
            env=env,
            stdout=log_fh if log_fh is not None else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if log_fh is not None else subprocess.DEVNULL,
            start_new_session=True,
        )
        log.info("bot-adapter: spawned pid=%d agent_id=%s tmux=%s bin=%s log=%s",
                 proc.pid, agent_id, tmux_session, bin_path,
                 str(log_path) if log_fh is not None else "DEVNULL")
        return proc
    except OSError as e:
        if log_fh is not None:
            try: log_fh.close()
            except OSError: pass
        log.warning("bot-adapter: spawn failed agent_id=%s: %s", agent_id, e)
        return None
    finally:
        # Popen 가 fd 를 dup 했으므로 parent 쪽 fd 는 닫아도 자식은 계속 씀.
        if log_fh is not None:
            try: log_fh.close()
            except OSError: pass
