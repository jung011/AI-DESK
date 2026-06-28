"""attachment ORM — t_ai_message_attachment.

채팅 첨부 (옵션 A — 휴먼↔AI 만). 파일 = BYTEA inline 저장.
- 5MB limit (app.core.config message_attachment_max_bytes)
- attachment 는 message 보다 먼저 upload 됨. message_id 는 link 시점에 UPDATE.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MessageAttachment(Base):
    __tablename__ = "t_ai_message_attachment"

    attachment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # 0003 — task 첨부 path. message_id 와 task_id 둘 다 nullable — 한 attachment row 가
    # 둘 중 하나의 owner 만 가짐. 옛 message 첨부 row 들은 task_id=NULL 그대로.
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_agent_id: Mapped[str] = mapped_column(String(36), index=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
