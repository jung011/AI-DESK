"""auth business logic — Spring LoginServiceImpl 와 1:1.

signup / authenticate / refresh / sign-out / me.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.agents.models import AiAgent
from app.auth.models import RefreshToken, User
from app.auth.repository import AuthRepository
from app.auth.schemas import AuthenticatedUser
from app.core.config import get_settings
from app.core.security import hash_password, verify_password

log = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuthRepository(db)

    # ---- signup ----

    def signup(self, login_id: str, raw_password: str) -> User | None:
        """신규 계정 + 휴먼 entity 동시 생성. 중복 loginId 면 None.

        Spring LoginServiceImpl.signup 과 동일 흐름:
        1. loginId normalize (trim + lower)
        2. 중복 검사
        3. t_user insert (password bcrypt)
        4. t_ai_agent 에 휴먼 entity insert (model='human', tmuxSession='__human__:<sn>')
        5. created_at 까지 채워서 반환
        """
        normalized = login_id.strip().lower()
        if self.repo.exists_by_login_id(normalized):
            return None

        user = User(
            login_id=normalized,
            password=hash_password(raw_password),
            display_name=normalized,
            role="USER",
        )
        self.repo.insert_user(user)

        # 휴먼 entity — partner-centric 채팅창에서 사용자 본인의 발신자 row.
        human = AiAgent(
            agent_id=str(uuid.uuid4()),
            agent_name="휴먼",
            owner_account_sn=user.account_sn,
            workspace_dir="",
            tmux_session=f"__human__:{user.account_sn}",
            status="active",
            model="human",
            type="human",
        )
        self.db.add(human)

        self.db.commit()
        self.db.refresh(user)
        return user

    # ---- authenticate ----

    def authenticate(self, login_id: str, raw_password: str) -> User | None:
        """이메일/비번 검증. 실패 시 None."""
        normalized = login_id.strip().lower()
        user = self.repo.find_by_login_id(normalized)
        if user is None:
            return None
        if not verify_password(raw_password, user.password):
            return None
        return user

    def record_last_login(self, account_sn: int) -> None:
        self.repo.update_last_login(account_sn)
        self.db.commit()

    def get_active_account(self, account_sn: int) -> User | None:
        return self.repo.find_by_account_sn(account_sn)

    # ---- JWT 발급 ----

    def create_access_token(self, user: User) -> str:
        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": user.login_id,
            "accountSn": user.account_sn,
            "role": user.role,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=settings.jwt_access_expiration_seconds)).timestamp()),
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def _create_refresh_token(self, user: User, jti: str) -> str:
        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": user.login_id,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=settings.jwt_refresh_expiration_seconds)).timestamp()),
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    # ---- refresh token rotation ----

    def issue_new_refresh_token(self, user: User) -> str:
        """첫 발급 — 새 family + 새 jti."""
        family_id = str(uuid.uuid4())
        return self._issue_refresh(user, family_id)

    def _issue_refresh(self, user: User, family_id: str) -> str:
        jti = str(uuid.uuid4())
        token = self._create_refresh_token(user, jti)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = datetime.utcnow() + timedelta(seconds=settings.jwt_refresh_expiration_seconds)
        self.repo.insert_refresh(
            RefreshToken(
                jti=jti,
                account_sn=user.account_sn,
                login_id=user.login_id,
                family_id=family_id,
                token_hash=token_hash,
                revoked_yn="N",
                expires_at=expires_at,
            )
        )
        self.db.commit()
        return token

    def rotate_refresh_token(self, token_str: str) -> tuple[User, str, str] | None:
        """옛 refresh token → 새 access + 새 refresh (같은 family, 새 jti).

        실패 케이스 모두 None 반환:
        - decode 실패 (signature / expired)
        - DB 안 record 없음
        - revoked=Y (= reuse 시도 → family 전체 폐기 + None)
        - tokenHash 불일치
        - User row 없음
        """
        try:
            claims = jwt.decode(token_str, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except JWTError:
            return None

        jti = claims.get("jti")
        if not jti:
            return None

        stored = self.repo.find_refresh_by_jti(jti)
        if stored is None:
            return None

        if stored.revoked_yn == "Y":
            # reuse 감지 — family 전체 폐기
            log.warning("refresh token reuse detected: login_id=%s family=%s", stored.login_id, stored.family_id)
            self.repo.revoke_family(stored.login_id, stored.family_id)
            self.db.commit()
            return None

        if hashlib.sha256(token_str.encode("utf-8")).hexdigest() != stored.token_hash:
            return None

        user = self.repo.find_by_account_sn(stored.account_sn)
        if user is None:
            return None

        # 옛 jti 폐기 + 같은 family 의 새 jti 발급
        self.repo.revoke_refresh_by_jti(jti)
        new_refresh = self._issue_refresh(user, stored.family_id)
        new_access = self.create_access_token(user)
        return user, new_access, new_refresh

    # ---- sign-out ----

    def sign_out(self, login_id: str) -> None:
        self.repo.delete_all_refresh_by_login_id(login_id)
        self.db.commit()

    # ---- JWT decode (deps 가 사용) ----

    @staticmethod
    def decode_access_token(token: str) -> AuthenticatedUser | None:
        try:
            claims = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except JWTError:
            return None
        login_id = claims.get("sub")
        account_sn = claims.get("accountSn")
        role = claims.get("role")
        if not login_id or account_sn is None or not role:
            return None
        return AuthenticatedUser(login_id=login_id, account_sn=int(account_sn), role=role)
