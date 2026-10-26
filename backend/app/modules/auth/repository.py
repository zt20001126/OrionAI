from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User


def get_user(session: Session, account: str) -> User | None:
    return session.scalar(select(User).where(User.account == account))


def create_user(
    session: Session,
    account: str,
    password_hash: str,
    created_at: datetime,
) -> User | None:
    user = User(
        account=account,
        password_hash=password_hash,
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


def update_last_login(session: Session, user: User, timestamp: datetime) -> None:
    user.last_login_at = timestamp
    session.commit()


def update_password(session: Session, user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    session.commit()
