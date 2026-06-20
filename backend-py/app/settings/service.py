"""settings business logic — Spring SettingService 와 1:1.

setting key:
- 'a2a_workspace' : 사내 동료 AI 와 소통하는 워크스페이스 경로
- 'workrole_file' : 신규 AI 부트스트랩 시 읽힐 작업 규칙 파일 경로

code-server URL: env (settings.code_server_url) — 임베드용 web vscode.
"""
import logging
import re
import socket
import uuid
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.agents.models import AiAgent
from app.agents.repository import AgentRepository
from app.settings.repository import SettingRepository

log = logging.getLogger(__name__)

KEY_A2A_WORKSPACE = "a2a_workspace"
KEY_WORKROLE_FILE = "workrole_file"

ME_TMUX_PREFIX = "aidesk-self-"
ME_MODEL = "claude-opus-4-7"
_EMPLOYEE_KEY_SAFE = re.compile(r"[^a-z0-9_-]")


def _derive_employee_key(login_id: str | None) -> str:
    """login_id → tmux session 호환 employee key. Spring deriveEmployeeKey 와 동등.

    예: 'liki@kaflix.com' → 'liki', 'wood' → 'wood'.
    """
    if not login_id:
        return ""
    head = login_id.strip().lower()
    if "@" in head:
        head = head.split("@", 1)[0]
    return _EMPLOYEE_KEY_SAFE.sub("", head)


class SettingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SettingRepository(db)

    # ---- a2a workspace ----

    def get_a2a_workspace(self, account_sn: int) -> str:
        return self.repo.select_value(account_sn, KEY_A2A_WORKSPACE) or ""

    def set_a2a_workspace(self, account_sn: int, login_id: str, path: str) -> int:
        """워크스페이스 저장 + (me) AI agent upsert.

        Returns:
            rc 0 = 성공, 1 = 빈 경로
        """
        if not path or not path.strip():
            return 1
        self.repo.upsert_value(account_sn, KEY_A2A_WORKSPACE, path)
        self._upsert_me_agent(path, account_sn, _derive_employee_key(login_id))
        self.db.commit()
        return 0

    def _upsert_me_agent(self, workspace_dir: str, owner_account_sn: int, employee_key: str) -> None:
        """(me) agent 를 사무실 AI 그룹(t_ai_agent) 에 등록/갱신.

        식별 키 = tmux_session 'aidesk-self-{employeeKey}'. 워크스페이스 옮겨도 같은 row 유지.
        Spring SettingService.upsertMeAgent 와 1:1.
        """
        if not employee_key:
            log.warning("upsert_me_agent: employee key 추출 실패 — skip")
            return

        session = ME_TMUX_PREFIX + employee_key
        agent_repo = AgentRepository(self.db)
        existing = agent_repo.find_by_tmux_session(session)
        if existing:
            if existing.workspace_dir == workspace_dir:
                log.info("upsert_me_agent: workspace 동일 — skip (agentId=%s)", existing.agent_id)
                return
            n = agent_repo.update_workspace_dir(existing.agent_id, workspace_dir, owner_account_sn)
            log.info("upsert_me_agent: workspace 갱신 agentId=%s updated=%d", existing.agent_id, n)
            return

        new_agent = AiAgent(
            agent_id=str(uuid.uuid4()),
            agent_name=f"{employee_key} (me)",
            owner_account_sn=owner_account_sn,
            workspace_dir=workspace_dir,
            tmux_session=session,
            status="active",
            model=ME_MODEL,
            agent_type="me",
        )
        agent_repo.insert(new_agent)
        log.info("upsert_me_agent: 신규 (me) 등록 agentId=%s", new_agent.agent_id)

    # ---- workrole file ----

    def get_workrole_file(self, account_sn: int) -> str:
        return self.repo.select_value(account_sn, KEY_WORKROLE_FILE) or ""

    def set_workrole_file(self, account_sn: int, path: str) -> None:
        self.repo.upsert_value(account_sn, KEY_WORKROLE_FILE, path or "")
        self.db.commit()

    # ---- code-server probe ----

    @staticmethod
    def get_code_server(url: str) -> tuple[str, bool]:
        """url 이 살아있는지 TCP probe (700ms). Spring 의 SettingService.getCodeServer 와 동등."""
        url = (url or "").strip()
        if not url:
            return "", False
        alive = False
        try:
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = parsed.port
            if port is None:
                port = 443 if parsed.scheme == "https" else 80
            with socket.create_connection((host, port), timeout=0.7):
                alive = True
        except (OSError, ValueError) as e:
            log.debug("code-server probe failed: url=%s err=%s", url, e)
        return url, alive
