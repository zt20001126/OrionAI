"""封装 Gitee 身份在 users 表中的持久化操作。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models.user import User


def get_user_by_gitee_id(session: Session, gitee_id: str) -> User | None:
    """按唯一 Gitee ID 查询用户；输入：Gitee 用户 ID；输出：用户或空值；调用方：Gitee Service。"""
    return session.scalar(select(User).where(User.gitee_id == gitee_id))


def create_gitee_user(
    session: Session,
    gitee_id: str,
    nickname: str | None,
    avatar_url: str | None,
    created_at: datetime,
) -> User | None:
    """创建无邮箱 Gitee 用户；唯一约束负责并发去重；调用方：Gitee 登录 Service。"""
    user = User(
        account=None,
        password_hash=None,
        is_guest=False,
        gitee_id=gitee_id,
        nickname=(nickname or "")[:20] or None,
        avatar_url=avatar_url,
        created_at=created_at,
        last_login_at=created_at,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    session.refresh(user)
    return user


def bind_gitee_id(session: Session, user: User, gitee_id: str) -> None:
    """给现有用户写入 Gitee ID；保留邮箱、密码、资料和业务关联。"""
    user.gitee_id = gitee_id
    session.commit()
