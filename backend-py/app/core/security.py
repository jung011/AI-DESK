"""JWT encode/decode + password hash.

Spring 의 PasswordEncoder (bcrypt) 와 호환 — passlib bcrypt 가 같은 해시 포맷 사용.
JWT secret 은 helm secret 'aidesk-ai-desk' 의 jwt-secret-key (env JWT_SECRET_KEY) 그대로.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

# bcrypt 직접 사용 (passlib 의 self-check 가 bcrypt 4.x 와 호환 X). $2a/$2b prefix 의
# 표준 bcrypt 해시라 Spring BCryptPasswordEncoder 와 양방향 호환.
_BCRYPT_MAX_BYTES = 72


def _truncate(raw: str) -> bytes:
    """bcrypt 의 72-byte 한계 — 그 이상이면 truncate. Spring 도 동일 한계."""
    return raw.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(raw: str) -> str:
    """Spring `passwordEncoder.encode(rawPassword)` 와 동일한 bcrypt 해시 생성."""
    return bcrypt.hashpw(_truncate(raw), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    """Spring `passwordEncoder.matches(raw, hashed)` 와 동일한 bcrypt 검증.

    Spring 이 만든 해시 ($2a$...) 를 FastAPI 가 verify 가능, 그 반대도 가능.
    """
    try:
        return bcrypt.checkpw(_truncate(raw), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    expires_seconds: int | None = None,
) -> str:
    """JWT access token 발급.

    Args:
        subject: 보통 account_sn 또는 login_id (자유)
        extra_claims: 추가 claim (예: account_sn, login_id, agent_id)
        expires_seconds: 만료 (초). 기본 = settings.jwt_expire_seconds
    """
    expires_seconds = expires_seconds or settings.jwt_expire_seconds
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_seconds)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """JWT 검증 + claim 반환.

    Raises:
        JWTError — 만료 / 서명 불일치 / 형식 오류
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        raise JWTError(f"invalid token: {e}") from e
