"""create t_ai_client_event — frontend critical 진단 event 영구 저장.

nav-debug 의 *원인 모를 새로고침* 같은 사고 진단용. K8s pod replace 박혀도
DB 에 영구 저장 박혀 사고 시점 trace 잡힘.

저장 대상 = location.reload / href-set / assign / replace / keydown:refresh /
beforeunload:snapshot / window:error 같은 *critical* event 만 (volume 낮음).

Revision ID: 0004_create_client_event
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_create_client_event"
down_revision = "0003_create_ai_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "t_ai_client_event",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("account_sn", sa.Integer(), nullable=True),  # 인증 없을 수도 있어 nullable
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("route", sa.String(length=500), nullable=True),
        sa.Column("data", sa.Text(), nullable=True),  # JSON string
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_t_ai_client_event_created_at", "t_ai_client_event", ["created_at"])
    op.create_index("ix_t_ai_client_event_event_type", "t_ai_client_event", ["event_type"])
    op.create_index("ix_t_ai_client_event_account_sn", "t_ai_client_event", ["account_sn"])


def downgrade() -> None:
    op.drop_index("ix_t_ai_client_event_account_sn", table_name="t_ai_client_event")
    op.drop_index("ix_t_ai_client_event_event_type", table_name="t_ai_client_event")
    op.drop_index("ix_t_ai_client_event_created_at", table_name="t_ai_client_event")
    op.drop_table("t_ai_client_event")
