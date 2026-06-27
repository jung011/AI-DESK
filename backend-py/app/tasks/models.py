"""AiTask ORM — t_ai_task.

대시보드 상단 *task 패널* 통해 사용자가 박는 backlog. AI 가 mcp tool
(`task_start` / `task_complete`) 호출로 lifecycle 명시 신호.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiTask(Base):
    __tablename__ = "t_ai_task"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    content: Mapped[str] = mapped_column(Text)
    # status = 'todo' | 'in_progress' | 'done' | 'stuck' | 'canceled'
    status: Mapped[str] = mapped_column(String(20), default="todo", server_default="todo", index=True)
    requester_account_sn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
