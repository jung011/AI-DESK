"""env 기반 설정 — pydantic-settings.

helm ConfigMap / Secret 의 env 가 그대로 매핑됨 (대소문자 무관, '_' delimited).
"""
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # DB — 두 가지 입력 패턴:
    # 1) DB_URL 직접 (SQLAlchemy URL — dev / sqlite test 용)
    # 2) Spring 의 SPRING_DATASOURCE_URL/_USERNAME/_PASSWORD (prod helm ConfigMap+Secret)
    #    jdbc:postgresql://host:5432/dbname → postgresql+psycopg://user:pw@host:5432/dbname
    db_url: str = Field(default="sqlite:///./dev.db")
    spring_datasource_url: str | None = Field(default=None, alias="SPRING_DATASOURCE_URL")
    spring_datasource_username: str | None = Field(default=None, alias="SPRING_DATASOURCE_USERNAME")
    spring_datasource_password: str | None = Field(default=None, alias="SPRING_DATASOURCE_PASSWORD")

    @model_validator(mode="after")
    def _compose_db_url(self):
        """Spring 의 3개 env 가 있으면 SQLAlchemy URL 자동 조립."""
        if self.spring_datasource_url is None:
            return self
        jdbc = self.spring_datasource_url
        user = self.spring_datasource_username or ""
        pw = self.spring_datasource_password or ""
        if jdbc.startswith("jdbc:postgresql://"):
            host_db = jdbc[len("jdbc:postgresql://"):]
            self.db_url = f"postgresql+psycopg://{user}:{pw}@{host_db}"
        elif jdbc.startswith("jdbc:mysql://"):
            host_db = jdbc[len("jdbc:mysql://"):]
            self.db_url = f"mysql+pymysql://{user}:{pw}@{host_db}"
        return self

    # JWT — helm ConfigMap (env) + Secret 매핑
    jwt_secret_key: str = Field(default="dev-secret-do-not-use-in-prod-min-32-bytes-required", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_access_expiration_seconds: int = Field(default=24 * 60 * 60, alias="JWT_ACCESS_EXPIRATION_SECONDS")
    jwt_refresh_expiration_seconds: int = Field(default=7 * 24 * 60 * 60, alias="JWT_REFRESH_EXPIRATION_SECONDS")

    # Cookie — Spring 의 CookieUtil 와 동일 이름 사용 → 기존 사용자 cookie 호환
    cookie_access_name: str = "accessToken"
    cookie_refresh_name: str = "refreshToken"
    cookie_secure: bool = False
    cookie_domain: str = Field(default="", alias="COOKIE_DOMAIN")  # 빈 = host-only (dev). prod 는 ".kaflix.internal"

    # CORS — Spring helm ConfigMap 이 "a,b,c" 콤마 string 으로 send. pydantic-settings 의 list 파싱이
    # JSON 배열만 허용해서 string 으로 받고 split. .allowed_origins property 가 실제 list.
    cors_allowed_origins: str = Field(default="", alias="CORS_ALLOWED_ORIGINS")
    cors_allowed_hosts: str = ".kaflix.internal"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # helper-pkg
    helper_pkg_dir: str = "/app/helper"

    # 메시지 정책 — Spring ConfigMap 의 MESSAGES_POLICY_* 와 매핑
    message_context_limit_pct: int = Field(default=90, alias="MESSAGES_POLICY_CONTEXT_LIMIT_PCT")
    message_hop_limit: int = Field(default=10, alias="MESSAGES_POLICY_HOP_LIMIT")
    message_rate_limit_per_minute: int = Field(default=30, alias="MESSAGES_POLICY_RATE_LIMIT_PER_MINUTE")
    message_content_max_length: int = Field(default=4000, alias="MESSAGES_CONTENT_MAX_LENGTH")

    # 외부 URL (frontend 사용)
    metaverse_url: str = ""

    # code-server (사이드패널 임베드 web vscode) — 현재 비활성 기능과 짝
    code_server_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
