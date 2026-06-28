"""create t_ai_task — agent task 큐 (옵션 H).

사용자가 대시보드 상단 task 패널 통해 박는 backlog. AI 가 *task_start* / *task_complete*
mcp tool 호출로 lifecycle 명시 신호.

t_ai_message_attachment.task_id 컬럼 추가 — 옛 message 첨부 path 재사용. attachment row 가
message_id 또는 task_id 중 하나 박힘 (둘 다 nullable).

Revision ID: 0003_create_ai_task
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_create_ai_task"
down_revision = "0002_create_message_attachment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "t_ai_task",
        sa.Column("task_id", sa.String(length=36), primary_key=True),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # status = 'todo' | 'in_progress' | 'done' | 'stuck' | 'canceled'
        sa.Column("status", sa.String(length=20), nullable=False, server_default="todo"),
        sa.Column("requester_account_sn", sa.Integer(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_t_ai_task_agent_id", "t_ai_task", ["agent_id"])
    op.create_index("ix_t_ai_task_status", "t_ai_task", ["status"])

    # 옛 t_ai_message_attachment 의 message_id 컬럼 옆에 task_id 추가 — attachment row 가
    # message 또는 task 중 하나의 첨부. 옛 row 는 task_id=NULL 그대로.
    op.add_column(
        "t_ai_message_attachment",
        sa.Column("task_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_t_ai_message_attachment_task_id",
        "t_ai_message_attachment",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_t_ai_message_attachment_task_id", table_name="t_ai_message_attachment")
    op.drop_column("t_ai_message_attachment", "task_id")
    op.drop_index("ix_t_ai_task_status", table_name="t_ai_task")
    op.drop_index("ix_t_ai_task_agent_id", table_name="t_ai_task")
    op.drop_table("t_ai_task")
