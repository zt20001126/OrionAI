"""为用户技能关联保存技能名称快照。

Revision ID: 0007_add_user_skill_name
Revises: 0006_snowflake_skill_ids
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_user_skill_name"
down_revision: str | None = "0006_snowflake_skill_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增技能名称列，回填已有记录后设为必填。"""

    op.add_column(
        "user_skills",
        sa.Column(
            "skill_name",
            sa.String(length=100),
            nullable=True,
            comment="用户关联技能名称快照",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE user_skills "
            "SET skill_name = (SELECT skills.name FROM skills "
            "WHERE skills.id = user_skills.skill_id)"
        )
    )
    op.alter_column(
        "user_skills",
        "skill_name",
        existing_type=sa.String(length=100),
        nullable=False,
        comment="用户关联技能名称快照",
    )


def downgrade() -> None:
    """移除用户技能关联中的技能名称快照。"""

    op.drop_column("user_skills", "skill_name")
