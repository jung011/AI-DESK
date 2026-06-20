"""alter t_ai_message.content TYPE TEXT (Spring schema 의 VARCHAR(1000) 한도 제거)

옛 Spring schema = `content VARCHAR(1000)`. FastAPI ORM 은 Text 인데 prod DB column
한도 1000 라 4000자 메시지 INSERT 시 fail. rc36 (config max 4000) + rc37 (startup
inline ALTER) 의 *임시 fix* 를 정식 migration 으로 정리.

idempotent — PostgreSQL 의 동일 type 재지정은 noop.

Revision ID: 0001_alter_content_text
Create Date: 2026-06-20
"""
from alembic import op


revision = "0001_alter_content_text"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE t_ai_message ALTER COLUMN content TYPE TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE t_ai_message ALTER COLUMN content TYPE VARCHAR(1000)")
