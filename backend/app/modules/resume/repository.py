"""封装简历记录的用户范围 SQL 操作。"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.resume.models import Resume


def get_resume(session: Session, user_id: int) -> Resume | None:
    return session.scalar(select(Resume).where(Resume.user_id == user_id))


def save_resume(
    session: Session,
    user_id: int,
    *,
    content: dict[str, Any],
    style_config: dict[str, Any],
    expected_updated_at: datetime | None,
) -> Resume | None:
    current = get_resume(session, user_id)
    if current is None:
        if expected_updated_at is not None:
            return None
        session.add(Resume(user_id=user_id, content=content, style_config=style_config))
        session.flush()
        return get_resume(session, user_id)
    if expected_updated_at is None or current.updated_at != expected_updated_at:
        return None
    session.execute(
        update(Resume)
        .where(Resume.id == current.id, Resume.updated_at == expected_updated_at)
        .values(content=content, style_config=style_config, updated_at=func.now())
    )
    session.flush()
    return get_resume(session, user_id)


def update_content_if_unchanged(
    session: Session,
    user_id: int,
    *,
    expected_updated_at: datetime,
    content: dict[str, Any],
) -> bool:
    result = session.execute(
        update(Resume)
        .where(Resume.user_id == user_id, Resume.updated_at == expected_updated_at)
        .values(content=content, updated_at=func.now())
    )
    return result.rowcount == 1
