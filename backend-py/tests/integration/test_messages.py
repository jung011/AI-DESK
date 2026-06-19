"""messages 통합 테스트 — send + 정책 + list + unread + mark read + ack."""
import pytest
from sqlalchemy.orm import Session

from app.agents.models import AiAgent
from app.auth.models import User
from app.messages.models import Message


@pytest.fixture
def two_agents(db_session: Session) -> tuple[AiAgent, AiAgent]:
    """같은 user 의 internal agent 2개 — alice 의 sender + receiver."""
    user = User(login_id="alice@example.com", password="x", display_name="alice", role="USER")
    db_session.add(user)
    db_session.flush()

    sender = AiAgent(
        agent_id="sender-1",
        agent_name="sender",
        owner_account_sn=user.account_sn,
        workspace_dir="/tmp/a",
        tmux_session="aidesk-sender",
        status="idle",
        model="claude-opus-4-7",
        agent_type="internal",
    )
    receiver = AiAgent(
        agent_id="receiver-1",
        agent_name="receiver",
        owner_account_sn=user.account_sn,
        workspace_dir="/tmp/b",
        tmux_session="aidesk-receiver",
        status="idle",
        model="claude-opus-4-7",
        agent_type="internal",
        context_pct=50,
    )
    db_session.add_all([sender, receiver])
    db_session.commit()
    return sender, receiver


def test_send_success(client, two_agents, db_session):
    sender, receiver = two_agents
    rs = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "hello"},
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["result"] == 0
    assert body["data"]["status"] == "sent"
    assert body["data"]["fromAgentName"] == "sender"
    assert body["data"]["toAgentName"] == "receiver"
    assert body["data"]["content"] == "hello"

    # DB row
    row = db_session.query(Message).filter_by(from_agent_id=sender.agent_id).one()
    assert row.status == "sent"
    assert row.hop_count == 1


def test_send_self_message_blocked(client, two_agents):
    sender, _ = two_agents
    rs = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": sender.agent_id, "content": "x"},
    )
    body = rs.json()
    assert body["data"]["status"] == "failed"
    assert "self-message" in body["data"]["errorReason"]


def test_send_unknown_sender_failed(client, two_agents):
    _, receiver = two_agents
    rs = client.post(
        "/api/messages",
        json={"fromAgentId": "unknown", "toAgentId": receiver.agent_id, "content": "x"},
    )
    assert rs.json()["data"]["status"] == "failed"
    assert "발신 agent" in rs.json()["data"]["errorReason"]


def test_send_context_guard_rejects(client, two_agents, db_session):
    sender, receiver = two_agents
    receiver.context_pct = 95  # >= 90 default
    db_session.commit()
    rs = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "x"},
    )
    assert rs.json()["data"]["status"] == "failed"
    assert "컨텍스트" in rs.json()["data"]["errorReason"]


def test_send_1000char_limit_validation(client, two_agents):
    sender, receiver = two_agents
    rs = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "x" * 1001},
    )
    # Pydantic validation → 422
    assert rs.status_code == 422


def test_reply_chain_hop_count_increment(client, two_agents):
    sender, receiver = two_agents
    rs1 = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "1"},
    ).json()["data"]
    rs2 = client.post(
        "/api/messages",
        json={
            "fromAgentId": receiver.agent_id,
            "toAgentId": sender.agent_id,
            "content": "reply",
            "replyToMessageId": rs1["messageId"],
        },
    ).json()["data"]
    assert rs2["status"] == "sent"
    assert rs2["replyToMessageId"] == rs1["messageId"]


def test_hop_limit_blocks_deep_chain(client, two_agents, db_session):
    sender, receiver = two_agents
    # parent hop_count=10 (limit 10) — 11번째 시도 = fail
    parent = Message(
        message_id="parent-1",
        from_agent_id=sender.agent_id,
        to_agent_id=receiver.agent_id,
        content="root",
        hop_count=10,
        status="sent",
    )
    db_session.add(parent)
    db_session.commit()

    rs = client.post(
        "/api/messages",
        json={
            "fromAgentId": sender.agent_id,
            "toAgentId": receiver.agent_id,
            "content": "over",
            "replyToMessageId": "parent-1",
        },
    )
    assert rs.json()["data"]["status"] == "failed"
    assert "위임 깊이" in rs.json()["data"]["errorReason"]


def test_cross_user_internal_blocked(client, two_agents, db_session):
    sender, _ = two_agents

    # 다른 user 의 internal agent
    bob = User(login_id="bob@example.com", password="x", display_name="bob", role="USER")
    db_session.add(bob)
    db_session.flush()
    bob_agent = AiAgent(
        agent_id="bob-internal",
        agent_name="bob-internal",
        owner_account_sn=bob.account_sn,
        workspace_dir="/",
        tmux_session="aidesk-bob",
        status="idle",
        model="claude-opus-4-7",
        agent_type="internal",
    )
    db_session.add(bob_agent)
    db_session.commit()

    rs = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": "bob-internal", "content": "x"},
    )
    assert rs.json()["data"]["status"] == "failed"
    assert "통신 권한" in rs.json()["data"]["errorReason"]


def test_list_in_out_all_direction(client, two_agents):
    sender, receiver = two_agents
    client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "1"},
    )
    client.post(
        "/api/messages",
        json={"fromAgentId": receiver.agent_id, "toAgentId": sender.agent_id, "content": "2"},
    )

    # all
    rs = client.get(f"/api/messages?agentId={sender.agent_id}&direction=all")
    assert len(rs.json()["data"]["list"]) == 2
    # in (sender 가 수신)
    rs = client.get(f"/api/messages?agentId={sender.agent_id}&direction=in")
    assert len(rs.json()["data"]["list"]) == 1
    # out (sender 가 발신)
    rs = client.get(f"/api/messages?agentId={sender.agent_id}&direction=out")
    assert len(rs.json()["data"]["list"]) == 1


def test_unread_count_and_mark_read(client, two_agents):
    sender, receiver = two_agents
    sent = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "hi"},
    ).json()["data"]

    rs = client.get(f"/api/messages/unread-count?agentId={receiver.agent_id}")
    assert rs.json()["data"]["totalUnread"] == 1
    assert rs.json()["data"]["byAgent"][0]["agentName"] == "sender"

    # mark read
    rs = client.patch(f"/api/messages/{sent['messageId']}/read?agentId={receiver.agent_id}")
    assert rs.json()["result"] == 0

    rs = client.get(f"/api/messages/unread-count?agentId={receiver.agent_id}")
    assert rs.json()["data"]["totalUnread"] == 0


def test_mark_read_wrong_recipient_404(client, two_agents):
    sender, receiver = two_agents
    sent = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "hi"},
    ).json()["data"]

    rs = client.patch(f"/api/messages/{sent['messageId']}/read?agentId={sender.agent_id}")
    # sender 가 본인이 받은 거 아닌 메시지 read 시도
    assert rs.json()["result"] == 404


def test_ack_marks_delivered(client, two_agents, db_session):
    sender, receiver = two_agents
    sent = client.post(
        "/api/messages",
        json={"fromAgentId": sender.agent_id, "toAgentId": receiver.agent_id, "content": "hi"},
    ).json()["data"]

    rs = client.post(f"/api/messages/{sent['messageId']}/ack")
    assert rs.json()["result"] == 0

    row = db_session.query(Message).filter_by(message_id=sent["messageId"]).one()
    assert row.status == "delivered"
    assert row.delivered_at is not None


def test_detail_404_for_unknown(client):
    rs = client.get("/api/messages/unknown-msg")
    assert rs.json()["result"] == 404
