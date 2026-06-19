"""env 기반 설정 — pydantic-settings.

helm ConfigMap / Secret 의 env 가 그대로 매핑됨 (대소문자 무관, '_' delimited).
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # DB
    db_url: str = Field(default="mysql+pymysql://aidesk:aidesk@localhost:3306/aidesk")

    # JWT — Spring 의 jwt.secret-key / access-expiration-seconds / refresh-expiration-seconds 와 동일 매핑
    jwt_secret_key: str = Field(default="dev-secret-do-not-use-in-prod-min-32-bytes-required")
    jwt_algorithm: str = "HS256"
    jwt_access_expiration_seconds: int = 24 * 60 * 60     # 24h
    jwt_refresh_expiration_seconds: int = 7 * 24 * 60 * 60  # 7d

    # Cookie — Spring 의 CookieUtil 와 동일 이름 사용 → 기존 사용자 cookie 호환
    cookie_access_name: str = "accessToken"
    cookie_refresh_name: str = "refreshToken"
    cookie_secure: bool = False
    cookie_domain: str = ""  # 빈 값 = host-only (dev). prod 는 ".kaflix.internal"

    # CORS — JSON 배열 or 콤마 분리 둘 다 허용 (pydantic-settings 가 list 파싱)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    cors_allowed_hosts: str = ".kaflix.internal"

    # helper-pkg
    helper_pkg_dir: str = "/app/helper"

    # 메시지 정책
    message_context_limit_pct: int = 90
    message_hop_limit: int = 10
    message_content_max_length: int = 1000

    # 외부 URL (frontend 사용)
    metaverse_url: str = ""

    # code-server (사이드패널 임베드 web vscode) — 현재 비활성 기능과 짝
    code_server_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
