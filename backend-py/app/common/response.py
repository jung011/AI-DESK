"""공통 응답 envelope — Spring 의 ResponseJson<T> 호환.

frontend 가 result / data / message 키 매칭 중. 다른 패턴 (code/message) 은
인증 실패 시점에만 사용 (exceptions.py 의 _jwt_error).
"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    """`{result, message, data}` 형식의 응답 wrapper."""

    result: int = 0
    message: str = ""
    data: T | None = None


def ok(data: T | None = None, message: str = "") -> ApiEnvelope[T]:
    return ApiEnvelope[T](result=0, message=message, data=data)


def fail(code: int, message: str) -> ApiEnvelope[None]:
    return ApiEnvelope[None](result=code, message=message, data=None)
