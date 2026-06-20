"""auth Pydantic schemas — Spring 의 Login*Vo 와 1:1.

frontend 는 result/data/message envelope 안 data 필드에서 이 schema 를 본다.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginSignupRq(BaseModel):
    login_id: EmailStr = Field(alias="loginId", min_length=3, max_length=255)
    password: str = Field(min_length=4, max_length=100)

    model_config = ConfigDict(populate_by_name=True)


class LoginAuthenticateRq(BaseModel):
    login_id: str = Field(alias="loginId", min_length=1)
    password: str = Field(min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class LoginSignupRs(BaseModel):
    """signup 직후 응답 — 인증 토큰 없음 (UI 에서 별도 login 호출)."""

    account_sn: int = Field(serialization_alias="accountSn")
    login_id: str = Field(serialization_alias="loginId")
    display_name: str = Field(serialization_alias="displayName")
    role: str
    created_at: datetime | None = Field(default=None, serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LoginAuthenticateRs(BaseModel):
    """authenticate / refresh 응답 — body 에는 식별 클레임만. 토큰은 쿠키로."""

    account_sn: int = Field(serialization_alias="accountSn")
    login_id: str = Field(serialization_alias="loginId")
    display_name: str = Field(serialization_alias="displayName")
    role: str

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AuthMeRs(BaseModel):
    account_sn: int = Field(serialization_alias="accountSn")
    login_id: str = Field(serialization_alias="loginId")
    display_name: str = Field(serialization_alias="displayName")
    role: str
    created_at: datetime | None = Field(default=None, serialization_alias="createdAt")
    last_login_dt: datetime | None = Field(default=None, serialization_alias="lastLoginDt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AuthenticatedUser(BaseModel):
    """JWT decode 후 request 안에서 전달. Spring 의 AuthenticatedUser 와 동등."""

    account_sn: int
    login_id: str
    role: str
