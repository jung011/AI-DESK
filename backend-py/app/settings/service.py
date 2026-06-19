"""settings business logic — Spring SettingService 와 1:1.

setting key:
- 'a2a_workspace' : 사내 동료 AI 와 소통하는 워크스페이스 경로
- 'workrole_file' : 신규 AI 부트스트랩 시 읽힐 작업 규칙 파일 경로

code-server URL: env (settings.code_server_url) — 임베드용 web vscode.
"""
import logging
import socket
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.settings.repository import SettingRepository

log = logging.getLogger(__name__)

KEY_A2A_WORKSPACE = "a2a_workspace"
KEY_WORKROLE_FILE = "workrole_file"


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

        TODO: agents 도메인 본격 포팅 후 (me) agent upsert 코드 추가.
        현재는 setting upsert 만 — agents 포팅 turn 에 합쳐 완성.
        """
        if not path or not path.strip():
            return 1
        self.repo.upsert_value(account_sn, KEY_A2A_WORKSPACE, path)
        # TODO(agents-port): upsertMeAgent(path, account_sn, deriveEmployeeKey(login_id))
        self.db.commit()
        return 0

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
