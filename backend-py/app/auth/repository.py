"""auth DB 접근 — Spring LoginMapper 와 1:1.

SQLAlchemy 2.0 style. transaction 은 service 가 with Session() 패턴으로 관리.
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.models import RefreshToken, User


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- User (t_user) ----

    def find_by_login_id(self, login_id: str) -> User | None:
        return self.db.execute(select(User).where(User.login_id == login_id)).scalar_one_or_none()

    def find_by_account_sn(self, account_sn: int) -> User | None:
        return self.db.execute(select(User).where(User.account_sn == account_sn)).scalar_one_or_none()

    def exists_by_login_id(self, login_id: str) -> bool:
        return self.db.execute(select(User.account_sn).where(User.login_id == login_id)).scalar_one_or_none() is not None

    def insert_user(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()  # account_sn 채워짐
        return user

    def update_last_login(self, account_sn: int) -> None:
        self.db.execute(
            update(User).where(User.account_sn == account_sn).values(last_login_dt=datetime.now(tz=timezone.utc))
        )

    # ---- RefreshToken (t_refresh_token) ----

    def find_refresh_by_jti(self, jti: str) -> RefreshToken | None:
        return self.db.execute(select(RefreshToken).where(RefreshToken.jti == jti)).scalar_one_or_none()

    def insert_refresh(self, token: RefreshToken) -> RefreshToken:
        self.db.add(token)
        self.db.flush()
        return token

    def revoke_refresh_by_jti(self, jti: str) -> None:
        self.db.execute(
            update(RefreshToken).where(RefreshToken.jti == jti).values(revoked_yn="Y")
        )

    def revoke_family(self, login_id: str, family_id: str) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.login_id == login_id, RefreshToken.family_id == family_id)
            .values(revoked_yn="Y")
        )

    def delete_all_refresh_by_login_id(self, login_id: str) -> None:
        # delete 보다 revoke 가 audit 보존 측면 안전. Spring 의 deleteRefreshTokenByLoginId 와 행위 동등.
        self.db.execute(
            update(RefreshToken).where(RefreshToken.login_id == login_id).values(revoked_yn="Y")
        )
