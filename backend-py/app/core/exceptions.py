"""공통 예외 + handler — Spring 의 ResponseJson envelope 호환 응답."""
import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import ExpiredSignatureError, JWTError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.response import fail

log = logging.getLogger(__name__)


class ApiException(Exception):
    """비즈니스 예외 — code + message + http_status.

    frontend 가 result/data/message envelope 의 result 코드를 매칭.
    """

    def __init__(self, code: int, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class NotAuthenticated(ApiException):
    """`{code: "NA", message: "Not authenticated"}` 와 호환되는 인증 실패."""

    def __init__(self, message: str = "Not authenticated") -> None:
        super().__init__(code=401, message=message, http_status=401)


class TokenExpired(ApiException):
    """`{code: "ET"}` — access token 만료. frontend interceptor 가 자동 refresh trigger.

    NotAuthenticated 와 구분 필수 — 옛 패턴 (둘 다 NA) 시 frontend 가 refresh 안 시도 → 즉시 logout.
    """

    def __init__(self, message: str = "Token expired") -> None:
        super().__init__(code=401, message=message, http_status=401)


class Forbidden(ApiException):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(code=403, message=message, http_status=403)


def register_exception_handlers(app: FastAPI) -> None:
    """app 의 글로벌 exception handler 등록."""

    @app.exception_handler(NotAuthenticated)
    async def _not_authenticated(_: Request, exc: NotAuthenticated) -> JSONResponse:
        # frontend 가 {code: "NA"} 시그널로 로그인 화면 redirect — envelope 형식 X
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": "NA", "message": exc.message},
        )

    @app.exception_handler(TokenExpired)
    async def _token_expired(_: Request, exc: TokenExpired) -> JSONResponse:
        # frontend 가 {code: "ET"} 시그널로 /api/auth/refresh 자동 호출 + 원 요청 재시도
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": "ET", "message": exc.message},
        )

    @app.exception_handler(ApiException)
    async def _api_exception(_: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=fail(exc.code, exc.message).model_dump(),
        )

    @app.exception_handler(ExpiredSignatureError)
    async def _expired_signature(_: Request, exc: ExpiredSignatureError) -> JSONResponse:
        # ExpiredSignatureError 는 JWTError 의 subclass — 더 구체적인 handler 가 먼저 매칭됨.
        # 직접 raise 안 했을 때 (예: decode 안 catch 한 path) 의 안전망. 정상 path 는 deps 의
        # TokenExpired 가 먼저 처리.
        log.info("JWT expired (fallback handler): %s", exc)
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "ET", "message": "Token expired"},
        )

    @app.exception_handler(JWTError)
    async def _jwt_error(_: Request, exc: JWTError) -> JSONResponse:
        log.info("JWT error: %s", exc)
        # frontend 가 'NA' / 'Not authenticated' 시그널로 로그인 화면 redirect
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "NA", "message": "Not authenticated"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.status_code, str(exc.detail)).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # pydantic 의 detail 을 그대로 노출 — frontend 의 form validation 메시지
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"result": 422, "message": "validation error", "data": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=fail(500, "internal server error").model_dump(),
        )
