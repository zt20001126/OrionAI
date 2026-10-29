"""封装记忆训练图片素材的 SQLAlchemy 查询。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.memory_training.models import MemoryImage


def pick_random_enabled_image(
    session: Session,
    *,
    excluded_image_id: int | None = None,
) -> MemoryImage | None:
    """从启用图片中随机选择一张，优先排除用户上次训练的素材。"""

    statement = select(MemoryImage).where(MemoryImage.enabled.is_(True))
    if excluded_image_id is not None:
        statement = statement.where(MemoryImage.id != excluded_image_id)
    image = session.scalar(statement.order_by(func.random()).limit(1))
    if image is None and excluded_image_id is not None:
        image = session.scalar(
            select(MemoryImage)
            .where(MemoryImage.enabled.is_(True))
            .order_by(func.random())
            .limit(1)
        )
    return image


def get_image_by_url(session: Session, image_url: str) -> MemoryImage | None:
    """按公开访问链接检查素材是否已登记。"""

    return session.scalar(select(MemoryImage).where(MemoryImage.image_url == image_url))


def add_image(session: Session, image_url: str) -> MemoryImage:
    """登记一条已上传并配置为公开读的 OSS 图片链接。"""

    image = MemoryImage(image_url=image_url, enabled=True)
    session.add(image)
    session.flush()
    return image
