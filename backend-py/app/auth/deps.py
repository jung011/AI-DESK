"""auth dependency — current_user (request 의 cookie 또는 Authorization header 에서 JWT 읽기).

Spring 의 @AuthenticationPrincipal AuthenticatedUser principal 와 동등.
없으면 NotAuthenticated 예외 — exception_handler 가 {code: "NA"} 응답.
"""
import logging

from fastapi import Cookie, Header, Request
from jose import ExpiredSignatureError

from app.auth.schemas import AuthenticatedUser
from app.auth.service import AuthService
from app.core.config import get_settings
from app.core.exceptions import NotAuthenticated, TokenExpired

settings = get_settings()
auth_log = logging.getLogger("app.auth")


def _log_auth_fail(reason: str, request: Request | None, has_cookie: bool, has_bearer: bool) -> None:
    """logout 사고 재발 시 K8s log 의 *정확한 진단* 박힘. clientLog 보다 영구.

    옛 사고 (2026-06-29 12:55 logout) 박은 거 console 로 만 박혀있어 진단 불가능
    사고 박혀있었어. server log 로 모든 NA / ET 가 영구 박혀있어야 root 잡힘.
    """
    path = request.url.path if request else "?"
    ua = (request.headers.get("user-agent") or "-")[:80] if request else "?"
    fwd = (request.headers.get("x-forwarded-for") or "-")[:40] if request else "?"
    auth_log.warning(
        "auth-fail reason=%s path=%s has_cookie=%s has_bearer=%s fwd=%s ua=%s",
        reason, path, has_cookie, has_bearer, fwd, ua,
    )


def current_user(
    request: Request,
    access_token_cookie: str | None = Cookie(default=None, alias="accessToken"),
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser:
    """JWT 우선순위: Bearer header > accessToken cookie."""
    has_bearer = bool(authorization and authorization.lower().startswith("bearer "))
    has_cookie = bool(access_token_cookie)
    token: str | None = None
    if has_bearer:
        token = authorization[7:].strip()  # type: ignore[index]
    elif has_cookie:
        token = access_token_cookie

    if not token:
        _log_auth_fail("no_token", request, has_cookie, has_bearer)
        raise NotAuthenticated()

    try:
        user = AuthService.decode_access_token(token)
    except ExpiredSignatureError:
        # frontend interceptor 가 ET 받으면 /api/auth/refresh 자동 호출 + 원 요청 재시도
        _log_auth_fail("ET_expired", request, has_cookie, has_bearer)
        raise TokenExpired()  # noqa: B904
    if user is None:
        # decode 했는데 None — signature / format invalid. NA 박힘. *진짜 사고 의 핵심*.
        _log_auth_fail("NA_invalid_jwt", request, has_cookie, has_bearer)
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
