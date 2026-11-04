"""为文旅评论匹配结果增加段落情感分类字段。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_tourism_sentiment"
down_revision: str | None = "0019_tourism_insight"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为现有结果项添加可空情感字段，保留所有历史结果。"""

    op.add_column(
        "comment_matches",
        sa.Column(
            "sentiment",
            sa.String(length=20),
            nullable=True,
            comment="拆分评论结果的情感倾向：positive、negative 或 objective",
        ),
    )
    op.create_check_constraint(
        "ck_comment_matches_sentiment",
        "comment_matches",
        "sentiment IS NULL OR sentiment IN ('positive', 'negative', 'objective')",
    )


def downgrade() -> None:
    """移除情感分类约束和字段，不影响其他分析结果列。"""

    op.drop_constraint(
        "ck_comment_matches_sentiment",
        "comment_matches",
        type_="check",
    )
    op.drop_column("comment_matches", "sentiment")
