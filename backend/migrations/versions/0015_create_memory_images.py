"""Create the memory training image catalogue.

Revision ID: 0015_create_memory_images
Revises: 0014_create_reminders
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_create_memory_images"
down_revision: str | None = "0014_create_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """创建仅保存图片公开访问链接和启用状态的素材表。"""

    op.create_table(
        "memory_images",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=False,
            nullable=False,
            comment="图片素材 Snowflake ID",
        ),
        sa.Column("image_url", sa.String(length=2048), nullable=False, comment="图片公开访问链接"),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="是否用于新训练",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="素材登记时间",
        ),
        sa.CheckConstraint("length(trim(image_url)) > 0", name="ck_memory_images_url_nonempty"),
        sa.PrimaryKeyConstraint("id", name="pk_memory_images"),
        sa.UniqueConstraint("image_url", name="uq_memory_images_image_url"),
        comment="记忆训练图片素材目录",
    )
    op.create_index(
        "ix_memory_images_enabled_id",
        "memory_images",
        ["id"],
        unique=False,
        postgresql_where=sa.text("enabled IS TRUE"),
    )


def downgrade() -> None:
    """删除记忆训练图片素材表。"""

    op.drop_index("ix_memory_images_enabled_id", table_name="memory_images")
    op.drop_table("memory_images")
