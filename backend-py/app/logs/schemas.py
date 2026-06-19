"""logs schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ActionLogCreateRq(BaseModel):
    agent_id: str = Field(alias="agentId", min_length=1)
    agent_name: str | None = Field(default=None, alias="agentName")
    session_id: str | None = Field(default=None, alias="sessionId")
    cwd: str | None = None
    tool: str | None = None
    category: str | None = None
    target: str | None = None
    summary: str | None = None

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
