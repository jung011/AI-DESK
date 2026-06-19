"""messages Pydantic — Spring Message*Vo 와 1:1."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings

_settings = get_settings()


class MessageCreateRq(BaseModel):
    from_agent_id: str = Field(alias="fromAgentId", min_length=1)
    to_agent_id: str = Field(alias="toAgentId", min_length=1)
    content: str = Field(min_length=1, max_length=_settings.message_content_max_length)
    reply_to_message_id: str | None = Field(default=None, alias="replyToMessageId")

    model_config = ConfigDict(populate_by_name=True)


class MessageItem(BaseModel):
    """Spring MessageItemRsVo."""

    message_id: str = Field(serialization_alias="messageId")
    from_agent_id: str = Field(serialization_alias="fromAgentId")
    from_agent_name: str | None = Field(default=None, serialization_alias="fromAgentName")
    to_agent_id: str = Field(serialization_alias="toAgentId")
    to_agent_name: str | None = Field(default=None, serialization_alias="toAgentName")
    content: str
    reply_to_message_id: str | None = Field(default=None, serialization_alias="replyToMessageId")
    status: str
    error_reason: str | None = Field(default=None, serialization_alias="errorReason")
    created_at: datetime | None = Field(default=None, serialization_alias="createdAt")
    delivered_at: datetime | None = Field(default=None, serialization_alias="deliveredAt")
    read_at: datetime | None = Field(default=None, serialization_alias="readAt")
    replied_at: datetime | None = Field(default=None, serialization_alias="repliedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageListRs(BaseModel):
    items: list[MessageItem] = Field(default_factory=list, serialization_alias="list")
    has_more: bool = Field(default=False, serialization_alias="hasMore")

    model_config = ConfigDict(populate_by_name=True)


class AgentUnread(BaseModel):
    agent_id: str = Field(serialization_alias="agentId")
    agent_name: str = Field(serialization_alias="agentName")
    unread: int

    model_config = ConfigDict(populate_by_name=True)


class UnreadCountRs(BaseModel):
    total_unread: int = Field(serialization_alias="totalUnread")
    by_agent: list[AgentUnread] = Field(default_factory=list, serialization_alias="byAgent")

    model_config = ConfigDict(populate_by_name=True)
