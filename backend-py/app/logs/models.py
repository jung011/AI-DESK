"""logs ORM — t_ai_action_log. Spring schema.sql 과 1:1."""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActionLog(Base):
    __tablename__ = "t_ai_action_log"

    log_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool: Mapped[str] = mapped_column(String(50))         # NOT NULL — DDL
    category: Mapped[str] = mapped_column(String(20))     # NOT NULL — DDL
    target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
