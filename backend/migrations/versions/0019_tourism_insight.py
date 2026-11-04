"""创建文旅洞察评分规则、评论和匹配结果表。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_tourism_insight"
down_revision: str | None = "0018_membership_manual_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建当前用户独立的文旅分析数据表。"""
    op.create_table(
        "scoring_rules",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="评分子项 Snowflake ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="规则所属用户 ID"),
        sa.Column("major_item", sa.String(length=255), nullable=False, comment="评分大项"),
        sa.Column("minor_item", sa.String(length=255), nullable=False, comment="评分分项"),
        sa.Column("indicator_code", sa.String(length=100), nullable=False, comment="指标编号"),
        sa.Column("indicator_name", sa.String(length=500), nullable=False, comment="指标名称"),
        sa.Column("subitem_number", sa.String(length=100), nullable=False, comment="子项序号"),
        sa.Column("subitem_name", sa.String(length=500), nullable=False, comment="子项名称"),
        sa.Column("scoring_criterion", sa.Text(), nullable=False, comment="国标评分口径原文"),
        sa.Column("description", sa.Text(), nullable=True, comment="规则简要说明"),
        sa.Column("data_source_detail", sa.Text(), nullable=True, comment="适用证据数据源"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "indicator_code",
            "subitem_number",
            "subitem_name",
            name="uq_scoring_rules_user_item",
        ),
        comment="当前用户导入的景区评分规则子项",
    )
    op.create_index("ix_scoring_rules_user_id", "scoring_rules", ["user_id"])
    op.create_table(
        "ugc_comments",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="评论 Snowflake ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="评论所属用户 ID"),
        sa.Column(
            "source_type", sa.String(length=20), nullable=False, comment="来源类型：csv 或 manual"
        ),
        sa.Column("original_id", sa.String(length=255), nullable=True, comment="源平台评论标识"),
        sa.Column("nickname", sa.String(length=255), nullable=True, comment="用户昵称"),
        sa.Column("ugc_type", sa.String(length=100), nullable=True, comment="评论或笔记类型"),
        sa.Column("platform", sa.String(length=100), nullable=True, comment="评论平台来源"),
        sa.Column("title", sa.String(length=1000), nullable=True, comment="评论标题"),
        sa.Column("content", sa.Text(), nullable=False, comment="游客评论原文"),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), nullable=True, comment="原评论发布时间"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "platform", "original_id", name="uq_ugc_comments_import_id"),
        comment="用户导入或手动录入的游客评论",
    )
    op.create_index("ix_ugc_comments_user_created", "ugc_comments", ["user_id", "id"])
    op.create_table(
        "comment_matches",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="匹配记录 Snowflake ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="匹配所属用户 ID"),
        sa.Column("comment_id", sa.BigInteger(), nullable=False, comment="被分析评论 ID"),
        sa.Column("rule_id", sa.BigInteger(), nullable=True, comment="匹配规则 ID；未匹配时为空"),
        sa.Column("evidence", sa.Text(), nullable=True, comment="评论中的原文证据"),
        sa.Column("reason", sa.Text(), nullable=True, comment="匹配判断依据"),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="匹配状态：matched、review 或 unmatched",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="分析记录创建时间",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["comment_id"], ["ugc_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["scoring_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="游客评论与评分子项匹配结果",
    )
    op.create_index("ix_comment_matches_user_comment", "comment_matches", ["user_id", "comment_id"])
    op.create_index("ix_comment_matches_rule_id", "comment_matches", ["rule_id"])


def downgrade() -> None:
    """按外键依赖逆序删除文旅洞察数据表。"""
    op.drop_index("ix_comment_matches_rule_id", table_name="comment_matches")
    op.drop_index("ix_comment_matches_user_comment", table_name="comment_matches")
    op.drop_table("comment_matches")
    op.drop_index("ix_ugc_comments_user_created", table_name="ugc_comments")
    op.drop_table("ugc_comments")
    op.drop_index("ix_scoring_rules_user_id", table_name="scoring_rules")
    op.drop_table("scoring_rules")
