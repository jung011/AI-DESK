"""AI Agent ORM model — t_ai_agent.

auth/service.signup 이 휴먼 entity 를 insert 할 때도 사용. 본격 agents 도메인 포팅 시 더 많은
컬럼 / index / relation 추가.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AiAgent(Base):
    __tablename__ = "t_ai_agent"

    sn: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    owner_account_sn: Mapped[int] = mapped_column(Integer, index=True)
    workspace_dir: Mapped[str] = mapped_column(String(500), default="")
    tmux_session: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="idle")
    model: Mapped[str] = mapped_column(String(50), default="claude-opus-4-7")
    type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # me / internal / external / human
    context_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_desc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
