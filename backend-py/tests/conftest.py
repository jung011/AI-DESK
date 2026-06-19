"""pytest fixture — in-memory SQLite 격리 + TestClient.

prod 의 MySQL 과 SQL dialect 차이 있을 수 있음 — fixture 가 PyMySQL 또는 testcontainers 의
MySQL 로 변경 필요 시 본 파일만 수정.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Base.metadata 가 모든 도메인 model 을 알아야 create_all 이 동작 → 명시 import.
from app.agents.models import AiAgent  # noqa: F401
from app.auth.models import RefreshToken, User  # noqa: F401
from app.messages.models import Message  # noqa: F401
from app.settings.models import AideskSetting  # noqa: F401
from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    """매 test 마다 격리된 in-memory SQLite session."""
    # StaticPool — 모든 session 이 같은 in-memory connection 을 공유. 없으면 sessionmaker 가
    # 매 session 마다 새 connection → 새 :memory: DB 가 생겨 create_all 의 table 이 안 보임.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    """app 의 get_db 를 override — test session 주입."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_router_stubs_wire(client):
    """모든 도메인 router 가 정상 wire 됐는지 health probe 호출."""
    paths = [
        ("/api/auth/_health", "auth"),
        ("/api/agents/_health", "agents"),
        ("/api/agents/external/_health", "agents/external"),
        ("/api/messages/_health", "messages"),
        ("/api/desktop/_health", "desktop"),
        ("/api/helper/_health", "helper"),
        ("/api/colleagues/_health", "colleagues"),
        ("/api/settings/_health", "settings"),
        ("/api/_health", "logs"),
    ]
    for path, expected_router in paths:
        rs = client.get(path)
        assert rs.status_code == 200, f"{path} returned {rs.status_code}"
        body = rs.json()
        assert body["router"] == expected_router, f"{path} returned router={body['router']}"
