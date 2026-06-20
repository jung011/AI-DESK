"""external agent 통합 테스트 — create + rotate + revoke."""
import hashlib

from app.agents.models import AiAgent


def _login(client) -> dict:
    client.post("/api/auth/signup", json={"loginId": "alice@example.com", "password": "passw0rd"})
    rs = client.post("/api/auth/authenticate", json={"loginId": "alice@example.com", "password": "passw0rd"})
    return dict(rs.cookies)


def test_create_external_agent(client, db_session):
    cookies = _login(client)
    rs = client.post("/api/agents/external", json={"agentName": "카랑이"}, cookies=cookies)
    assert rs.status_code == 200
    body = rs.json()["data"]
    assert body["agentName"] == "카랑이"
    assert len(body["token"]) > 30  # URL-safe base64 token
    agent_id = body["agentId"]

    # DB row
    row = db_session.query(AiAgent).filter_by(agent_id=agent_id).one()
    assert row.agent_type == "external"
    assert row.model == "external"
    assert row.workspace_dir == "(external)"
    assert row.tmux_session == f"external-{agent_id}"
    assert row.status == "offline"
    # hash = sha256(token)
    expected = hashlib.sha256(body["token"].encode("utf-8")).hexdigest()
    assert row.bearer_token_hash == expected


def test_rotate_token_invalidates_old(client, db_session):
    cookies = _login(client)
    created = client.post("/api/agents/external", json={"agentName": "x"}, cookies=cookies).json()["data"]
    old_token = created["token"]
    old_hash = db_session.query(AiAgent).filter_by(agent_id=created["agentId"]).one().bearer_token_hash

    rs = client.post(f"/api/agents/external/{created['agentId']}/token", cookies=cookies)
    body = rs.json()["data"]
    new_token = body["token"]
    assert new_token != old_token

    db_session.expire_all()
    new_hash = db_session.query(AiAgent).filter_by(agent_id=created["agentId"]).one().bearer_token_hash
    assert new_hash != old_hash
    assert new_hash == hashlib.sha256(new_token.encode("utf-8")).hexdigest()


def test_revoke_token_nulls_hash(client, db_session):
    cookies = _login(client)
    created = client.post("/api/agents/external", json={"agentName": "x"}, cookies=cookies).json()["data"]
    rs = client.delete(f"/api/agents/external/{created['agentId']}/token", cookies=cookies)
    assert rs.status_code == 200

    db_session.expire_all()
    row = db_session.query(AiAgent).filter_by(agent_id=created["agentId"]).one()
    assert row.bearer_token_hash is None


def test_external_endpoints_require_auth(client):
    rs = client.post("/api/agents/external", json={"agentName": "x"})
    assert rs.status_code == 401
    rs = client.post("/api/agents/external/anything/token")
    assert rs.status_code == 401


def test_rotate_other_users_external_404(client, db_session):
    cookies_a = _login(client)
    created_a = client.post("/api/agents/external", json={"agentName": "ka"}, cookies=cookies_a).json()["data"]

    # bob 으로 로그인 + alice 의 token rotate 시도 → 404
    client.post("/api/auth/signup", json={"loginId": "bob@example.com", "password": "passw0rd"})
    rs_b = client.post("/api/auth/authenticate", json={"loginId": "bob@example.com", "password": "passw0rd"})
    cookies_b = dict(rs_b.cookies)

    rs = client.post(f"/api/agents/external/{created_a['agentId']}/token", cookies=cookies_b)
    assert rs.status_code == 404
