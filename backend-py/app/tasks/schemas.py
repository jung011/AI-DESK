"""task schemas — request / response DTO."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskAttachmentItem(BaseModel):
    attachment_id: str = Field(serialization_alias="attachmentId")
    original_filename: str = Field(serialization_alias="originalFilename")
    content_type: str = Field(serialization_alias="contentType")
    size_bytes: int = Field(serialization_alias="sizeBytes")

    model_config = ConfigDict(populate_by_name=True)


class TaskItem(BaseModel):
    task_id: str = Field(serialization_alias="taskId")
    agent_id: str = Field(serialization_alias="agentId")
    agent_name: str | None = Field(default=None, serialization_alias="agentName")
    content: str
    status: str  # todo / in_progress / done / stuck / canceled
    result: str | None = None
    created_at: datetime = Field(serialization_alias="createdAt")
    started_at: datetime | None = Field(default=None, serialization_alias="startedAt")
    completed_at: datetime | None = Field(default=None, serialization_alias="completedAt")
    attachments: list[TaskAttachmentItem] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class TaskListRs(BaseModel):
    items: list[TaskItem] = Field(default_factory=list)


class TaskCreateRq(BaseModel):
    agent_id: str = Field(alias="agentId")
    content: str
    attachment_ids: list[str] = Field(default_factory=list, alias="attachmentIds")

    model_config = ConfigDict(populate_by_name=True)


class TaskCompleteRq(BaseModel):
    result: str | None = None
