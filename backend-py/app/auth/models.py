"""auth ORM model — t_user + t_refresh_token.

Spring 의 LoginVo / RefreshTokenVo 와 1:1 매핑.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """t_user — 계정. Spring LoginVo 와 동일."""

    __tablename__ = "t_user"

    account_sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))  # bcrypt 해시
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="USER")
    last_login_dt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class RefreshToken(Base):
    """t_refresh_token — refresh token rotation 추적. Spring RefreshTokenVo 와 동일.

    family_id 로 reuse 감지 — 같은 family 의 옛 jti 재사용 시도 시 전체 family 폐기.
    token_hash = sha256(token) — 원본 token 은 cookie 에만, DB 엔 해시.
    """

    __tablename__ = "t_refresh_token"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_sn: Mapped[int] = mapped_column(Integer, index=True)
    login_id: Mapped[str] = mapped_column(String(255), index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex
    revoked_yn: Mapped[str] = mapped_column(String(1), default="N")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
