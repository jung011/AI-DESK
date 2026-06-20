"""logs schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ActionLogCreateRq(BaseModel):
    agent_id: str = Field(alias="agentId", min_length=1)
    agent_name: str | None = Field(default=None, alias="agentName")
    session_id: str | None = Field(default=None, alias="sessionId")
    # cwd 는 helper 가 보내지만 DB DDL 에 없음 — 받아 무시 (저장 X)
    cwd: str | None = None
    tool: str = Field(min_length=1, max_length=50)       # NOT NULL DDL
    category: str = Field(min_length=1, max_length=20)   # NOT NULL DDL
    target: str | None = None
    summary: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ClientLogRq(BaseModel):
    """frontend 에서 backend 적재용 로그 entry. console / localStorage 와 동등 정보.

    DB 저장 X — backend application logger (app.client channel) 만. K8s stdout 에 모임.
    """

    level: str = Field(default="warn", max_length=10)
    msg: str = Field(min_length=1, max_length=500)
    data: dict | None = None
    route: str | None = Field(default=None, max_length=300)

    model_config = ConfigDict(populate_by_name=True)


class LogFeedItem(BaseModel):
    """통합 피드 — type='message' / 'action' 분기."""

    type: str
    created_at: datetime = Field(serialization_alias="createdAt")
    category: str | None = None
    agent_id: str = Field(serialization_alias="agentId")
    agent_name: str | None = Field(default=None, serialization_alias="agentName")
    summary: str | None = None
    target: str | None = None

    model_config = ConfigDict(populate_by_name=True)
