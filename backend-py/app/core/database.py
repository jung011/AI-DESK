"""SQLAlchemy engine + Session + Base.

기존 DB schema 그대로 사용 — FastAPI 가 자동 생성 X.
schema 변경 = 운영팀 manual DDL (memory: db-schema-migration).
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# pool_pre_ping — Mac sleep/wake 후 stale connection 회피
# application_name (rc48) — pg_stat_activity 에서 leak source 즉시 추적 가능.
# 2026-06-22 사고 시 application_name 빈값이라 endpoint 매핑 어려움이 있었음.
# postgresql:// 가 아닌 driver (sqlite 등) 면 connect_args 가 무시될 수 있어
# postgresql 일 때만 적용.
_connect_args: dict = {}
if settings.db_url.startswith("postgresql"):
    _connect_args["application_name"] = "aidesk-backend"

engine = create_engine(
    settings.db_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base — 모든 ORM model 의 부모."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — request scope DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
