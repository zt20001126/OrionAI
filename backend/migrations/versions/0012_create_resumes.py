"""Create one JSONB resume per user and publish the resume assistant."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_create_resumes"
down_revision: str | None = "0011_generic_task_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="简历 Snowflake ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="简历所属用户"),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("style_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("jsonb_typeof(content) = 'object'", name="ck_resumes_content_object"),
        sa.CheckConstraint(
            "jsonb_typeof(style_config) = 'object'", name="ck_resumes_style_config_object"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_resumes_user_id"),
        comment="每个用户一份简历内容和排版设置",
    )
    op.execute(
        sa.text(
            "UPDATE skills SET status = 'published' "
            "WHERE code = 'resume_assistant' AND status = 'disabled'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE skills SET status = 'disabled' "
            "WHERE code = 'resume_assistant' AND status = 'published'"
        )
    )
    op.drop_table("resumes")
