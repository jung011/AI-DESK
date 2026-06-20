"""desktop 통합 테스트 — helper local-info reporter."""
from app.agents.models import AiAgent


def _make_agent(db_session, agent_id: str, ws: str, tmux: str, status: str = "idle") -> AiAgent:
    a = AiAgent(
        agent_id=agent_id,
        agent_name=agent_id,
        owner_account_sn=1,
        workspace_dir=ws,
        tmux_session=tmux,
        status=status,
        model="claude-opus-4-7",
        agent_type="internal",
    )
    db_session.add(a)
    db_session.commit()
    return a


def test_local_info_matches_and_updates_status(client, db_session):
    _make_agent(db_session, "a1", "/ws/a", "aidesk-a", status="idle")

    rs = client.post(
        "/api/desktop/local-info",
        json={
            "workspaces": [{"workspaceDir": "/ws/a", "status": "active"}],
            "tmuxSessions": [{"name": "aidesk-a"}],
        },
    )
    assert rs.status_code == 200
    body = rs.json()["data"]
    assert body["totalWorkspaces"] == 1
    assert body["matchedAgents"] == 1
    assert body["updatedAgents"] == 1

    db_session.expire_all()
    agent = db_session.query(AiAgent).filter_by(agent_id="a1").one()
    assert agent.status == "active"


def test_local_info_tmux_factcheck_forces_offline(client, db_session):
    """agent.tmux_session 이 보고된 list 에 없으면 status='offline' 강제."""
    _make_agent(db_session, "a2", "/ws/b", "aidesk-b", status="idle")

    rs = client.post(
        "/api/desktop/local-info",
        json={
            "workspaces": [{"workspaceDir": "/ws/b", "status": "active"}],
            "tmuxSessions": [],  # aidesk-b 없음
        },
    )
    assert rs.json()["data"]["updatedAgents"] == 1
    db_session.expire_all()
    assert db_session.query(AiAgent).filter_by(agent_id="a2").one().status == "offline"


def test_local_info_compacting_stick(client, db_session):
    """status='compacting' 인 agent 는 helper 의 active override 차단."""
    _make_agent(db_session, "a3", "/ws/c", "aidesk-c", status="compacting")

    rs = client.post(
        "/api/desktop/local-info",
        json={
            "workspaces": [{"workspaceDir": "/ws/c", "status": "active"}],
            "tmuxSessions": [{"name": "aidesk-c"}],
        },
    )
    body = rs.json()["data"]
    assert body["matchedAgents"] == 1
    # updated_agents = 0 (compacting stick — status 변경 안 함)
    assert body["updatedAgents"] == 0
    db_session.expire_all()
    assert db_session.query(AiAgent).filter_by(agent_id="a3").one().status == "compacting"


def test_local_info_empty_workspaces(client):
    rs = client.post("/api/desktop/local-info", json={"workspaces": [], "tmuxSessions": []})
    assert rs.json()["data"]["totalWorkspaces"] == 0
    assert rs.json()["data"]["matchedAgents"] == 0
