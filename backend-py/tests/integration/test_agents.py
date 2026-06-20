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


def test_list_with_caller_agent_channel_aware(client, db_session):
    """mcp 의 list_agents 호출 — callerAgentId 동봉 + channel-aware filter."""
    # signup → user row + 휴먼 entity 자동
    cookies = _login(client, "a@x.com")
    _login(client, "b@x.com")  # bob signup (cookies 는 사용 안 함, alice 로 인증 유지)
    alice = db_session.query(User).filter_by(login_id="a@x.com").one()
    bob = db_session.query(User).filter_by(login_id="b@x.com").one()
    # alice 로 다시 인증 (마지막 _login 호출이 bob 으로 cookies 박았을 수 있음)
    cookies = _login(client, "a@x.com")

    # alice 의 (me) + internal
    alice_me = AiAgent(
        agent_id="alice-me", agent_name="a (me)", owner_account_sn=alice.account_sn,
        workspace_dir="/a", tmux_session="aidesk-self-a", status="active",
        model="claude-opus-4-7", agent_type="me",
    )
    alice_int = AiAgent(
        agent_id="alice-int", agent_name="alice-internal", owner_account_sn=alice.account_sn,
        workspace_dir="/x", tmux_session="aidesk-ai", status="idle",
        model="claude-opus-4-7", agent_type="internal",
    )
    # bob (다른 user) 의 (me) + external
    bob_me = AiAgent(
        agent_id="bob-me", agent_name="b (me)", owner_account_sn=bob.account_sn,
        workspace_dir="/b", tmux_session="aidesk-self-b", status="active",
        model="claude-opus-4-7", agent_type="me",
    )
    bob_ext = AiAgent(
        agent_id="bob-ext", agent_name="bob-external", owner_account_sn=bob.account_sn,
        workspace_dir="/b", tmux_session="aidesk-ext-b", status="active",
        model="claude-opus-4-7", agent_type="external",
    )
    db_session.add_all([alice_me, alice_int, bob_me, bob_ext])
    db_session.commit()

    # callerAgentId = alice_int (channel A). A/A sameUser + BOTH 의 sameUser 만.
    rs = client.get("/api/agents?callerAgentId=alice-int", cookies=cookies)
    ids = {a["agentId"] for a in rs.json()["data"]["list"]}
    assert "alice-me" in ids       # sameUser BOTH+A
    assert "alice-int" not in ids  # self
    assert "bob-me" not in ids     # cross-user BOTH+A
    assert "bob-ext" not in ids    # A↔B 차단

    # callerAgentId = bob_ext (channel B). B/B sameUser + BOTH/BOTH cross-user.
    rs = client.get("/api/agents?callerAgentId=bob-ext", cookies=cookies)
    ids = {a["agentId"] for a in rs.json()["data"]["list"]}
    assert "bob-me" in ids         # sameUser BOTH+B
    assert "alice-me" not in ids   # cross-user BOTH+B → sameUser only
    assert "bob-ext" not in ids    # self


def test_realtime_partners_filled_from_messages(client, two_agents_for_realtime, db_session):
    sender, receiver = two_agents_for_realtime
    client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "hi"},
    )
    rs = client.get("/api/agents/realtime")
    by_id = {a["agentId"]: a for a in rs.json()["data"]}
    assert receiver.agent_id in by_id[sender.agent_id]["partners"]
    assert sender.agent_id in by_id[receiver.agent_id]["partners"]


import pytest

from app.agents.models import AiAgent
from app.auth.models import User


@pytest.fixture
def two_agents_for_realtime(db_session):
    u = User(login_id="rt@x.com", password="x", display_name="rt", role="USER")
    db_session.add(u)
    db_session.flush()
    s = AiAgent(
        agent_id="rt-sender",
        agent_name="rt-sender",
        owner_account_sn=u.account_sn,
        workspace_dir="/",
        tmux_session="aidesk-rts",
        status="active",
        model="claude-opus-4-7",
        agent_type="internal",
    )
    r = AiAgent(
        agent_id="rt-receiver",
        agent_name="rt-receiver",
        owner_account_sn=u.account_sn,
        workspace_dir="/",
        tmux_session="aidesk-rtr",
        status="active",
        model="claude-opus-4-7",
        agent_type="internal",
    )
    db_session.add_all([s, r])
    db_session.commit()
    return s, r
