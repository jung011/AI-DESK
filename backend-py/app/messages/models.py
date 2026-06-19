"""messages ORM — t_message. Spring MessageVo 와 1:1."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Message(Base):
    """t_message — 1:1 메시지.

    status: pending / sent / delivered / read / failed / compacting-deferred.
    hop_count: reply chain 깊이 (bot↔bot loop 차단).
    """

    __tablename__ = "t_message"

    # PK = message_id (Spring 실제 schema)
    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    from_agent_id: Mapped[str] = mapped_column(String(36), index=True)
    to_agent_id: Mapped[str] = mapped_column(String(36), index=True)
    content: Mapped[str] = mapped_column(Text)
    reply_to_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    root_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    hop_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
