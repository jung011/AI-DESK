"""colleagues 통합 테스트 — 사내 동료 디렉토리.

본인 외 user 의 (me) AI + 본인의 external AI 합산.
"""
from datetime import datetime, timezone

from app.agents.models import AiAgent
from app.auth.models import User


def _login(client, email: str) -> dict:
    client.post("/api/auth/signup", json={"loginId": email, "password": "passw0rd"})
    rs = client.post("/api/auth/authenticate", json={"loginId": email, "password": "passw0rd"})
    return dict(rs.cookies)


def _add_me_agent(db_session, account_sn: int, key: str, updated_at: datetime | None = None) -> AiAgent:
    agent = AiAgent(
        agent_id=f"me-{key}",
        agent_name=f"{key} (me)",
        owner_account_sn=account_sn,
        workspace_dir=f"/tmp/{key}",
        tmux_session=f"aidesk-self-{key}",
        status="active",
        model="claude-opus-4-7",
        agent_type="me",
        updated_at=updated_at,
    )
    db_session.add(agent)
    db_session.commit()
    return agent


def test_colleagues_list_empty_when_only_me(client):
    cookies = _login(client, "alice@example.com")
    rs = client.get("/api/colleagues", cookies=cookies)
    assert rs.status_code == 200
    # 본인 외 user 없음 + 본인 external 없음 → 빈 list
    assert rs.json()["data"]["list"] == []


def test_colleagues_lists_other_users_me_agents(client, db_session):
    cookies_a = _login(client, "alice@example.com")

    # bob signup + bob 의 (me) agent 추가
    client.post("/api/auth/signup", json={"loginId": "bob@example.com", "password": "passw0rd"})
    bob = db_session.query(User).filter_by(login_id="bob@example.com").one()
    _add_me_agent(db_session, bob.account_sn, "bob", updated_at=datetime.now(timezone.utc))

    rs = client.get("/api/colleagues", cookies=cookies_a)
    rows = rs.json()["data"]["list"]
    assert len(rows) == 1
    assert rows[0]["loginId"] == "bob@example.com"
    assert rows[0]["meAgentName"] == "bob (me)"
    assert rows[0]["online"] is True


def test_colleagues_offline_when_updated_at_old(client, db_session):
    cookies_a = _login(client, "alice@example.com")
    client.post("/api/auth/signup", json={"loginId": "bob@example.com", "password": "passw0rd"})
    bob = db_session.query(User).filter_by(login_id="bob@example.com").one()
    # 1시간 전 — 5분 윈도우 밖
    old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    _add_me_agent(db_session, bob.account_sn, "bob", updated_at=old_ts)

    rs = client.get("/api/colleagues", cookies=cookies_a)
    rows = rs.json()["data"]["list"]
    assert rows[0]["online"] is False


def test_colleagues_includes_own_external_agents(client, db_session):
    cookies_a = _login(client, "alice@example.com")
    alice = db_session.query(User).filter_by(login_id="alice@example.com").one()

    # 본인의 external AI 추가
    ext = AiAgent(
        agent_id="ext-karang",
        agent_name="글로벌 카랑이",
        owner_account_sn=alice.account_sn,
        workspace_dir="/tmp/global",
        tmux_session="aidesk-karang",
        status="active",
        model="claude-opus-4-7",
        agent_type="external",
    )
    db_session.add(ext)
    db_session.commit()

    rs = client.get("/api/colleagues", cookies=cookies_a)
    rows = rs.json()["data"]["list"]
    # 본인의 external 1개 (다른 user 없음)
    assert len(rows) == 1
    assert rows[0]["agentType"] == "external"
    assert rows[0]["meAgentName"] == "글로벌 카랑이"


def test_colleagues_requires_auth(client):
    rs = client.get("/api/colleagues")
    assert rs.status_code == 401
