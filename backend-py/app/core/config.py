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

    # JWT
    jwt_secret_key: str = Field(default="dev-secret-do-not-use-in-prod")
    jwt_algorithm: str = "HS256"
    jwt_expire_seconds: int = 24 * 60 * 60  # 24h
    jwt_refresh_expire_seconds: int = 7 * 24 * 60 * 60  # 7d
    jwt_cookie_name: str = "AIDESK_TOKEN"
    jwt_cookie_domain: str = ".kaflix.internal"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
