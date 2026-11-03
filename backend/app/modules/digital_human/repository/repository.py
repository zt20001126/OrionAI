"""只读查询现有会话表中的数字人会话，不定义新的持久化模型。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.conversations.models import Conversation

DIGITAL_HUMAN_SKILL_CODE = "digital_human"


def list_conversations(
    session: Session,
    user_id: int,
    *,
    limit: int,
    offset: int,
) -> list[Conversation]:
    """按最近更新时间倒序读取当前用户的数字人会话。"""

    statement = (
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.skill_code == DIGITAL_HUMAN_SKILL_CODE,
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def count_conversations(session: Session, user_id: int) -> int:
    """统计当前用户的数字人会话数量。"""

    statement = (
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.skill_code == DIGITAL_HUMAN_SKILL_CODE,
        )
    )
    return session.scalar(statement) or 0
