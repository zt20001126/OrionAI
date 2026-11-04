"""定义文旅洞察规则、UGC 评论和匹配结果的持久化模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id


class ScoringRule(Base):
    """当前用户导入的评分子项和原始评分口径。"""

    __tablename__ = "scoring_rules"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "indicator_code",
            "subitem_number",
            "subitem_name",
            name="uq_scoring_rules_user_item",
        ),
        Index("ix_scoring_rules_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, default=generate_snowflake_id, comment="评分子项 Snowflake ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="规则所属用户 ID",
    )
    major_item: Mapped[str] = mapped_column(String(255), nullable=False, comment="评分大项")
    minor_item: Mapped[str] = mapped_column(String(255), nullable=False, comment="评分分项")
    indicator_code: Mapped[str] = mapped_column(String(100), nullable=False, comment="指标编号")
    indicator_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="指标名称")
    subitem_number: Mapped[str] = mapped_column(String(100), nullable=False, comment="子项序号")
    subitem_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="子项名称")
    scoring_criterion: Mapped[str] = mapped_column(Text, nullable=False, comment="国标评分口径原文")
    description: Mapped[str | None] = mapped_column(Text, comment="规则简要说明")
    data_source_detail: Mapped[str | None] = mapped_column(Text, comment="适用证据数据源")


class UgcComment(Base):
    """导入或手动提交、供文旅评分分析的游客评价。"""

    __tablename__ = "ugc_comments"
    __table_args__ = (
        Index("ix_ugc_comments_user_created", "user_id", "id"),
        UniqueConstraint("user_id", "platform", "original_id", name="uq_ugc_comments_import_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, default=generate_snowflake_id, comment="评论 Snowflake ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="评论所属用户 ID",
    )
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="来源类型：csv 或 manual"
    )
    original_id: Mapped[str | None] = mapped_column(String(255), comment="源平台评论标识")
    nickname: Mapped[str | None] = mapped_column(String(255), comment="用户昵称")
    ugc_type: Mapped[str | None] = mapped_column(String(100), comment="评论或笔记类型")
    platform: Mapped[str | None] = mapped_column(String(100), comment="评论平台来源")
    title: Mapped[str | None] = mapped_column(String(1000), comment="评论标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="游客评论原文")
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="原评论发布时间"
    )


class CommentMatch(Base):
    """保存一条评论对应的规则匹配、证据和分析状态。"""

    __tablename__ = "comment_matches"
    __table_args__ = (
        CheckConstraint(
            "sentiment IS NULL OR sentiment IN ('positive', 'negative', 'objective')",
            name="ck_comment_matches_sentiment",
        ),
        Index("ix_comment_matches_user_comment", "user_id", "comment_id"),
        Index("ix_comment_matches_rule_id", "rule_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, default=generate_snowflake_id, comment="匹配记录 Snowflake ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="匹配所属用户 ID",
    )
    comment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ugc_comments.id", ondelete="CASCADE"),
        nullable=False,
        comment="被分析评论 ID",
    )
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("scoring_rules.id", ondelete="CASCADE"),
        comment="匹配规则 ID；未匹配时为空",
    )
    evidence: Mapped[str | None] = mapped_column(Text, comment="评论中的原文证据")
    reason: Mapped[str | None] = mapped_column(Text, comment="匹配判断依据")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="匹配状态：matched、review 或 unmatched"
    )
    sentiment: Mapped[str | None] = mapped_column(
        String(20), comment="拆分评论结果的情感倾向：positive、negative 或 objective"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="分析记录创建时间",
    )
