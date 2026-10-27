"""封装用户个人资料的数据库读取和更新。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User


def get_user_by_id(session: Session, user_id: int) -> User | None:
    """根据已认证的当前用户 ID 读取用户资料。"""

    return session.scalar(select(User).where(User.id == user_id))


def update_user_profile(
    session: Session,
    user_id: int,
    *,
    nickname: str,
    avatar_url: str | None,
) -> User | None:
    """保存昵称及可选头像 URL，并返回提交后的用户资料。"""

    user = session.scalar(select(User).where(User.id == user_id))
    if user is None:
        return None
    user.nickname = nickname
    if avatar_url is not None:
        user.avatar_url = avatar_url
    session.commit()
    session.refresh(user)
    return user
