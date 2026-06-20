"""create t_ai_message_attachment — 채팅 첨부 옵션 A (휴먼 ↔ AI).

파일 = BYTEA inline. 5MB limit (app-side). message_id 는 link 시점에 UPDATE
(upload 가 먼저, message 가 나중에 생성됨).

Revision ID: 0002_create_message_attachment
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_create_message_attachment"
down_revision = "0001_alter_content_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "t_ai_message_attachment",
        sa.Column("attachment_id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("owner_agent_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_t_ai_message_attachment_message_id",
        "t_ai_message_attachment",
        ["message_id"],
    )
    op.create_index(
        "ix_t_ai_message_attachment_owner_agent_id",
        "t_ai_message_attachment",
        ["owner_agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_t_ai_message_attachment_owner_agent_id", table_name="t_ai_message_attachment")
    op.drop_index("ix_t_ai_message_attachment_message_id", table_name="t_ai_message_attachment")
    op.drop_table("t_ai_message_attachment")
