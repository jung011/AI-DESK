"""pytest fixture — in-memory SQLite 로 격리 + TestClient.

prod 의 MySQL 과 SQL dialect 차이 있을 수 있음 — 그 경우 fixture 가 PyMySQL 또는
testcontainers 의 MySQL 로 변경 필요.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    """매 test 마다 격리된 in-memory SQLite session."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
    """모든 도메인 router 가 정상 wire 됐는지 확인."""
    for path in [
        "/api/auth/_health",
        "/api/agents/_health",
        "/api/agents/external/_health",
        "/api/messages/_health",
        "/api/desktop/_health",
        "/api/helper/_health",
        "/api/colleagues/_health",
        "/api/settings/_health",
        "/api/_health",  # logs router
    ]:
        rs = client.get(path)
        assert rs.status_code == 200, f"{path} returned {rs.status_code}"
        assert rs.json()["status"] == "stub"
