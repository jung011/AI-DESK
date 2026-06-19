"""auth router — /api/auth/*. Spring LoginController 와 1:1.

- POST /signup        : 회원가입
- POST /authenticate  : 로그인 + 쿠키 발급
- POST /refresh       : refresh token rotation (옛 jti 폐기 + 새 jti, family 유지)
- POST /sign-out      : refresh family 폐기 + 쿠키 clear
- GET  /me            : 현재 사용자
"""
from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.auth.cookies import clear_auth_cookie, set_auth_cookie
from app.auth.deps import current_user
from app.auth.schemas import (
    AuthenticatedUser,
    AuthMeRs,
    LoginAuthenticateRq,
    LoginAuthenticateRs,
    LoginSignupRq,
    LoginSignupRs,
)
from app.auth.service import AuthService
from app.common.response import ApiEnvelope, fail, ok
from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter()
settings = get_settings()


@router.get("/_health")
async def health() -> dict[str, str]:
    """domain probe — router wire 확인."""
    return {"router": "auth", "status": "ok"}


@router.post("/signup", response_model=ApiEnvelope[LoginSignupRs])
async def signup(body: LoginSignupRq, db: Session = Depends(get_db)) -> ApiEnvelope[LoginSignupRs]:
    service = AuthService(db)
    user = service.signup(body.login_id, body.password)
    if user is None:
        # Spring ResponseCode.FAIL_DUPLICATE 호환
        return fail(409, "이미 가입된 계정입니다.")  # type: ignore[return-value]
    return ok(LoginSignupRs.model_validate(user))


@router.post("/authenticate", response_model=ApiEnvelope[LoginAuthenticateRs])
async def authenticate(
    body: LoginAuthenticateRq,
    response: Response,
    db: Session = Depends(get_db),
) -> ApiEnvelope[LoginAuthenticateRs]:
    service = AuthService(db)
    user = service.authenticate(body.login_id, body.password)
    if user is None:
        return fail(401, "이메일 또는 비밀번호가 올바르지 않습니다.")  # type: ignore[return-value]
    service.record_last_login(user.account_sn)

    access_token = service.create_access_token(user)
    refresh_token = service.issue_new_refresh_token(user)

    # access 쿠키 Max-Age 도 refresh 만료와 동일 — 만료 토큰이 backend 에 도달해 ET 응답 → 자동 refresh
    max_age = settings.jwt_refresh_expiration_seconds
    set_auth_cookie(response, settings.cookie_access_name, access_token, max_age)
    set_auth_cookie(response, settings.cookie_refresh_name, refresh_token, max_age)

    return ok(LoginAuthenticateRs.model_validate(user))


@router.post("/refresh", response_model=ApiEnvelope[LoginAuthenticateRs])
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias="refreshToken"),
    db: Session = Depends(get_db),
) -> ApiEnvelope[LoginAuthenticateRs]:
    if not refresh_token:
        return fail(401, "refresh token 없음")  # type: ignore[return-value]

    service = AuthService(db)
    result = service.rotate_refresh_token(refresh_token)
    if result is None:
        # 만료 / 변조 / reuse — cookie clear 까지
        clear_auth_cookie(response, settings.cookie_access_name)
        clear_auth_cookie(response, settings.cookie_refresh_name)
        return fail(401, "refresh token invalid")  # type: ignore[return-value]

    user, new_access, new_refresh = result
    max_age = settings.jwt_refresh_expiration_seconds
    set_auth_cookie(response, settings.cookie_access_name, new_access, max_age)
    set_auth_cookie(response, settings.cookie_refresh_name, new_refresh, max_age)
    return ok(LoginAuthenticateRs.model_validate(user))


@router.post("/sign-out", response_model=ApiEnvelope[int])
async def sign_out(
    response: Response,
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[int]:
    service = AuthService(db)
    service.sign_out(user.login_id)
    clear_auth_cookie(response, settings.cookie_access_name)
    clear_auth_cookie(response, settings.cookie_refresh_name)
    return ok(0)


@router.get("/me", response_model=ApiEnvelope[AuthMeRs])
async def me(
    user: AuthenticatedUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiEnvelope[AuthMeRs]:
    service = AuthService(db)
    account = service.get_active_account(user.account_sn)
    if account is None:
        return fail(401, "사용자 row 없음")  # type: ignore[return-value]
    return ok(AuthMeRs.model_validate(account))
