"""JWT encode/decode + password hash.

Spring 의 PasswordEncoder (bcrypt) 와 호환 — passlib bcrypt 가 같은 해시 포맷 사용.
JWT secret 은 helm secret 'aidesk-ai-desk' 의 jwt-secret-key (env JWT_SECRET_KEY) 그대로.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    """Spring `passwordEncoder.encode(rawPassword)` 와 동일한 bcrypt 해시 생성."""
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    """Spring `passwordEncoder.matches(raw, hashed)` 와 동일한 bcrypt 검증.

    bcrypt 는 동일한 raw 에 대해 매번 다른 해시 (salt) 를 만들지만 verify 는 호환.
    Spring 이 만든 해시를 FastAPI 가 verify 가능, 그 반대도 가능.
    """
    return pwd_context.verify(raw, hashed)


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
