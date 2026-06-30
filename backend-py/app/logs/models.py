"""logs ORM — t_ai_action_log + t_ai_client_event."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActionLog(Base):
    __tablename__ = "t_ai_action_log"

    log_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(20))
    target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClientEvent(Base):
    """frontend critical 진단 event — pod replace 무관 영구 저장.

    nav-debug 의 *원인 모를 새로고침* 같은 사고 분석용. K8s stdout log 와 별개로
    DB 에 영구 보존. 저장 대상 = location.reload / href-set / assign / replace /
    keydown:refresh / beforeunload:snapshot / window:error 같은 critical event 만.
    """
    __tablename__ = "t_ai_client_event"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_sn: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    route: Mapped[str | None] = mapped_column(String(500), nullable=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
