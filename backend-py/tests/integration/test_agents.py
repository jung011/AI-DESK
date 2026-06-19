"""agents 통합 테스트 — CRUD + status + sameUser isolation."""
from app.agents.models import AiAgent


def _login(client, email: str = "alice@example.com", password: str = "passw0rd") -> dict:
    client.post("/api/auth/signup", json={"loginId": email, "password": password})
    rs = client.post("/api/auth/authenticate", json={"loginId": email, "password": password})
    return dict(rs.cookies)


def test_list_only_sees_own_user_agents(client, db_session):
    cookies_a = _login(client, "alice@example.com")
    # alice signup 시 휴먼 entity 1개 자동 — list 에 1개 있어야 함
    rs = client.get("/api/agents", cookies=cookies_a)
    assert rs.status_code == 200
    body = rs.json()
    assert body["result"] == 0
    items = body["data"]["list"]
    assert len(items) == 1
    assert items[0]["agentName"] == "휴먼"
    assert items[0]["type"] == "human"

    # bob signup → bob 의 휴먼 entity 도 alice 에게 안 보임
    cookies_b = _login(client, "bob@example.com")
    rs_b = client.get("/api/agents", cookies=cookies_b)
    assert len(rs_b.json()["data"]["list"]) == 1  # bob 의 휴먼

    # alice 도 여전히 1개만 (sameUser isolation)
    rs_a = client.get("/api/agents", cookies=cookies_a)
    assert len(rs_a.json()["data"]["list"]) == 1


def test_create_internal_agent(client, db_session):
    cookies = _login(client)
    rs = client.post(
        "/api/agents",
        json={"agentName": "리본 API", "workspaceDir": "/tmp/reborn", "model": "claude"},
        cookies=cookies,
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["result"] == 0
    assert body["data"]["agentName"] == "리본 API"
    assert body["data"]["type"] == "internal"
    assert body["data"]["model"] == "claude-opus-4-7"  # alias 풀이
    assert body["data"]["tmuxSession"].startswith("aidesk-")

    # list 에 2개 (휴먼 + 리본 API)
    rs = client.get("/api/agents", cookies=cookies)
    assert len(rs.json()["data"]["list"]) == 2


def test_detail_404_for_unknown(client):
    cookies = _login(client)
    rs = client.get("/api/agents/unknown-id", cookies=cookies)
    assert rs.json()["result"] == 404


def test_detail_returns_existing(client):
    cookies = _login(client)
    created = client.post(
        "/api/agents",
        json={"agentName": "셔틀", "workspaceDir": "/tmp/test-team3", "model": "claude"},
        cookies=cookies,
    ).json()["data"]

    rs = client.get(f"/api/agents/{created['agentId']}", cookies=cookies)
    assert rs.status_code == 200
    assert rs.json()["data"]["agentName"] == "셔틀"


def test_delete_soft_marks_deleted_at(client, db_session):
    cookies = _login(client)
    created = client.post(
        "/api/agents",
        json={"agentName": "to-delete", "workspaceDir": "/tmp/x", "model": "claude"},
        cookies=cookies,
    ).json()["data"]

    rs = client.delete(f"/api/agents/{created['agentId']}", cookies=cookies)
    assert rs.json()["result"] == 0

    # list 에서 사라짐
    items = client.get("/api/agents", cookies=cookies).json()["data"]["list"]
    assert all(i["agentId"] != created["agentId"] for i in items)

    # DB row 는 그대로 (soft delete)
    row = db_session.query(AiAgent).filter_by(agent_id=created["agentId"]).one()
    assert row.deleted_at is not None


def test_update_status_no_auth_required(client):
    cookies = _login(client)
    created = client.post(
        "/api/agents",
        json={"agentName": "shuttle", "workspaceDir": "/tmp/x", "model": "claude"},
        cookies=cookies,
    ).json()["data"]

    # status 갱신은 hook 호출 — 인증 없이도 가능
    rs = client.post(f"/api/agents/{created['agentId']}/status", json={"status": "compacting"})
    assert rs.json()["result"] == 0

    # 검증
    rs2 = client.get(f"/api/agents/{created['agentId']}", cookies=cookies)
    assert rs2.json()["data"]["status"] == "compacting"


def test_update_status_unknown_returns_404(client):
    rs = client.post("/api/agents/unknown/status", json={"status": "idle"})
    assert rs.json()["result"] == 404


def test_realtime_returns_all_active_agents(client):
    cookies = _login(client, "alice@example.com")
    client.post(
        "/api/agents",
        json={"agentName": "kerang", "workspaceDir": "/tmp/llm", "model": "claude"},
        cookies=cookies,
    )
    cookies_b = _login(client, "bob@example.com")  # noqa
    rs = client.get("/api/agents/realtime")
    assert rs.status_code == 200
    body = rs.json()
    # 모든 active agent (휴먼 alice + 휴먼 bob + kerang) = 3
    assert len(body["data"]) >= 3
    # 5필드 검증
    item = body["data"][0]
    assert "agentId" in item
    assert "name" in item
    assert "state" in item
    assert "partners" in item
    assert "lastSeenAt" in item


def test_create_requires_auth(client):
    rs = client.post("/api/agents", json={"agentName": "x", "workspaceDir": "/x", "model": "claude"})
    assert rs.status_code == 401
