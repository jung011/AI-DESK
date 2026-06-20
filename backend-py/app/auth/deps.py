"""auth dependency — current_user (request 의 cookie 또는 Authorization header 에서 JWT 읽기).

Spring 의 @AuthenticationPrincipal AuthenticatedUser principal 와 동등.
없으면 NotAuthenticated 예외 — exception_handler 가 {code: "NA"} 응답.
"""
from fastapi import Cookie, Header
from jose import ExpiredSignatureError

from app.auth.schemas import AuthenticatedUser
from app.auth.service import AuthService
from app.core.config import get_settings
from app.core.exceptions import NotAuthenticated, TokenExpired

settings = get_settings()


def current_user(
    access_token_cookie: str | None = Cookie(default=None, alias="accessToken"),
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser:
    """JWT 우선순위: Bearer header > accessToken cookie."""
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif access_token_cookie:
        token = access_token_cookie

    if not token:
        raise NotAuthenticated()

    try:
        user = AuthService.decode_access_token(token)
    except ExpiredSignatureError:
        # frontend interceptor 가 ET 받으면 /api/auth/refresh 자동 호출 + 원 요청 재시도
        raise TokenExpired()  # noqa: B904
    if user is None:
        raise NotAuthenticated()
    return user


def optional_user(
    access_token_cookie: str | None = Cookie(default=None, alias="accessToken"),
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser | None:
    """current_user 와 동일하지만 인증 안 되면 None — 일부 endpoint 가 익명도 허용.

    expired 도 None 반환 (익명 처리). 만약 frontend 가 자동 refresh 받으려면 current_user 사용.
    """
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif access_token_cookie:
        token = access_token_cookie
    if not token:
        return None
    try:
        return AuthService.decode_access_token(token)
    except ExpiredSignatureError:
        return None
