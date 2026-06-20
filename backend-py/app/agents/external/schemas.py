"""external agent schemas."""
from pydantic import BaseModel, ConfigDict, Field


class ExternalAgentCreateRq(BaseModel):
    agent_name: str = Field(alias="agentName", min_length=1, max_length=100)

    model_config = ConfigDict(populate_by_name=True)


class ExternalAgentTokenRs(BaseModel):
    """raw token 은 발급/rotate 시점 1회만 노출."""

    agent_id: str = Field(serialization_alias="agentId")
    agent_name: str = Field(serialization_alias="agentName")
    token: str  # raw — 호출자가 즉시 외부 service env 에 박아야 함

    model_config = ConfigDict(populate_by_name=True)
