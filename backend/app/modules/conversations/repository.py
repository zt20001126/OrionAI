"""封装会话和消息的 SQLAlchemy 查询，不处理 API 或 Agent 业务。"""

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.conversations.models import Conversation, Message


def create_conversation(
    session: Session, user_id: int, skill_code: str = "general_chat"
) -> Conversation:
    """创建属于指定用户的空会话。"""

    conversation = Conversation(user_id=user_id, skill_code=skill_code)
    session.add(conversation)
    session.flush()
    return conversation


def list_conversations(
    session: Session,
    user_id: int,
    *,
    limit: int,
    offset: int,
) -> list[Conversation]:
    """按更新时间倒序列出当前用户会话。"""

    statement = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def count_conversations(session: Session, user_id: int) -> int:
    """统计指定用户可访问的会话数量。"""

    statement = select(func.count()).select_from(Conversation).where(
        Conversation.user_id == user_id
    )
    return session.scalar(statement) or 0


def get_conversation(
    session: Session,
    user_id: int,
    conversation_id: int,
    *,
    for_update: bool = False,
) -> Conversation | None:
    """仅在当前用户所有权范围内查找会话。"""

    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def list_messages(
    session: Session,
    conversation_id: int,
    *,
    limit: int,
    offset: int,
) -> list[Message]:
    """按 ID 升序读取会话消息。"""

    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def get_latest_message(session: Session, conversation_id: int) -> Message | None:
    """读取会话最近一条用户可见消息，用于检查题卡等待状态。"""

    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(1)
    )
    return session.scalar(statement)


def has_messages(session: Session, conversation_id: int) -> bool:
    """检查会话是否已有用户可见消息。"""

    statement = select(Message.id).where(Message.conversation_id == conversation_id).limit(1)
    return session.scalar(statement) is not None


def create_message(
    session: Session,
    *,
    conversation_id: int,
    role: str,
    content: dict[str, object],
) -> Message:
    """新增一条用户可见消息。"""

    message = Message(conversation_id=conversation_id, role=role, content=content)
    session.add(message)
    session.flush()
    return message


def update_conversation_timestamp(conversation: Conversation, timestamp: datetime) -> None:
    """在成功写入交互后更新会话最近活动时间。"""

    conversation.updated_at = timestamp


def set_conversation_title_if_empty(
    session: Session,
    *,
    user_id: int,
    conversation_id: int,
    title: str,
) -> bool:
    """仅为当前用户的空标题会话写入标题，防止后续覆盖。"""

    statement = (
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            or_(Conversation.title.is_(None), Conversation.title == ""),
        )
        .values(title=title)
    )
    result = session.execute(statement)
    return result.rowcount == 1
