"""logs 통합 테스트 — action-logs + feed."""
from app.agents.models import AiAgent
from app.logs.models import ActionLog


def test_record_action_log(client, db_session):
    rs = client.post(
        "/api/action-logs",
        json={
            "agentId": "agent-x",
            "agentName": "Agent X",
            "sessionId": "sess-1",
            "tool": "Bash",
            "category": "shell",
            "target": "ls -la",
            "summary": "list",
        },
    )
    assert rs.status_code == 200
    log_id = rs.json()["data"]
    assert len(log_id) == 36  # uuid

    row = db_session.query(ActionLog).filter_by(log_id=log_id).one()
    assert row.agent_id == "agent-x"
    assert row.tool == "Bash"


def test_feed_merges_actions_and_messages(client, db_session):
    # action log — tool/category NOT NULL DDL → schema required
    client.post(
        "/api/action-logs",
        json={"agentId": "a1", "agentName": "A1", "tool": "Bash", "category": "shell", "summary": "ls"},
    )

    # 메시지 — 필요 agent 2개 추가
    a = AiAgent(
        agent_id="from-1", agent_name="from", owner_account_sn=1,
        workspace_dir="/", tmux_session="t1", status="idle", model="x", agent_type="internal",
    )
    b = AiAgent(
        agent_id="to-1", agent_name="to", owner_account_sn=1,
        workspace_dir="/", tmux_session="t2", status="idle", model="x", agent_type="internal",
    )
    db_session.add_all([a, b])
    db_session.commit()
    client.post(
        "/api/messages",
        json={"fromAgentId": "from-1", "toAgentId": "to-1", "content": "hi"},
    )

    rs = client.get("/api/logs?limit=10")
    body = rs.json()["data"]
    types = {item["type"] for item in body}
    assert "action" in types
    assert "message" in types


def test_feed_category_filter(client, db_session):
    client.post("/api/action-logs", json={"agentId": "a", "tool": "Bash", "category": "shell", "summary": "s1"})
    client.post("/api/action-logs", json={"agentId": "a", "tool": "Write", "category": "file", "summary": "s2"})

    rs = client.get("/api/logs?category=shell&limit=10")
    body = rs.json()["data"]
    # action 의 category=shell 만, message 제외
    assert all(item["type"] == "action" for item in body)
    assert all(item["category"] == "shell" for item in body)
