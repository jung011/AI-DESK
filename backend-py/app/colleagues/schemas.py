"""colleagues Pydantic — 사내 동료 디렉토리. Spring ColleagueRsVo 와 1:1."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ColleagueItem(BaseModel):
    account_sn: int = Field(serialization_alias="accountSn")
    login_id: str = Field(serialization_alias="loginId")
    display_name: str = Field(serialization_alias="displayName")
    me_agent_id: str | None = Field(default=None, serialization_alias="meAgentId")
    me_agent_name: str | None = Field(default=None, serialization_alias="meAgentName")
    me_status: str | None = Field(default=None, serialization_alias="meStatus")
    me_context_pct: int | None = Field(default=None, serialization_alias="meContextPct")
    me_workspace_dir: str | None = Field(default=None, serialization_alias="meWorkspaceDir")
    me_updated_at: datetime | None = Field(default=None, serialization_alias="meUpdatedAt")
    online: bool = False
    agent_type: str | None = Field(default=None, serialization_alias="agentType")

    model_config = ConfigDict(populate_by_name=True)


class ColleagueListRs(BaseModel):
    items: list[ColleagueItem] = Field(default_factory=list, serialization_alias="list")

    model_config = ConfigDict(populate_by_name=True)
