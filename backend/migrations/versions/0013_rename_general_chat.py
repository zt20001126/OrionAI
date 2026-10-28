"""Rename the general chat skill for display.

Revision ID: 0013_rename_general_chat
Revises: 0012_create_resumes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_rename_general_chat"
down_revision: str | None = "0012_create_resumes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE skills SET name = '对话助手' "
            "WHERE code = 'general_chat' AND name = '通用对话助手'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE user_skills SET skill_name = '对话助手' "
            "WHERE skill_name = '通用对话助手' AND skill_id IN ("
            "SELECT id FROM skills WHERE code = 'general_chat' AND name = '对话助手')"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE user_skills SET skill_name = '通用对话助手' "
            "WHERE skill_name = '对话助手' AND skill_id IN ("
            "SELECT id FROM skills WHERE code = 'general_chat' AND name = '对话助手')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE skills SET name = '通用对话助手' "
            "WHERE code = 'general_chat' AND name = '对话助手'"
        )
    )
