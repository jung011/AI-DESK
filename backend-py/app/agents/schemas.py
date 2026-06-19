"""agents Pydantic schemas — Spring 의 AgentVo / Item / List / Realtime 와 1:1."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentItem(BaseModel):
    """Spring AgentItemRsVo. 응답에 노출되는 필드."""

    agent_id: str = Field(serialization_alias="agentId")
    agent_name: str = Field(serialization_alias="agentName")
    workspace_dir: str = Field(default="", serialization_alias="workspaceDir")
    tmux_session: str = Field(default="", serialization_alias="tmuxSession")
    status: str
    task_desc: str | None = Field(default=None, serialization_alias="taskDesc")
    model: str
    context_pct: int | None = Field(default=None, serialization_alias="contextPct")
    started_at: datetime | None = Field(default=None, serialization_alias="startedAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")
    owner_account_sn: int = Field(serialization_alias="ownerAccountSn")
    type: str | None = None  # me / internal / external / human

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AgentListRs(BaseModel):
    items: list[AgentItem] = Field(default_factory=list, serialization_alias="list")

    model_config = ConfigDict(populate_by_name=True)


class AgentCreateRq(BaseModel):
    agent_name: str = Field(alias="agentName", min_length=1, max_length=100)
    workspace_dir: str = Field(alias="workspaceDir", default="")
    model: str = Field(default="claude")

    model_config = ConfigDict(populate_by_name=True)


class AgentStatusUpdateRq(BaseModel):
    status: str | None = None


class AgentRealtimeItem(BaseModel):
    """외부 시각화 BE (메타버스 3D 등) 가 소비하는 5필드 응답."""

    agent_id: str = Field(serialization_alias="agentId")
    name: str
    state: str  # working / idle / talking / awaiting_input / offline
    partners: list[str] = Field(default_factory=list)
    last_seen_at: datetime | None = Field(default=None, serialization_alias="lastSeenAt")

    model_config = ConfigDict(populate_by_name=True)
