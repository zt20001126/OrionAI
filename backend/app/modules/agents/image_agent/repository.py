"""封装图片助手任务结果的 SQLAlchemy 访问。"""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.agents.image_agent.models import ImageTaskResult


def create_task_result(
    session: Session,
    *,
    task_result_id: int,
    user_id: int,
    conversation_id: int,
    input_data: dict[str, Any],
) -> ImageTaskResult:
    result = ImageTaskResult(
        task_result_id=task_result_id,
        user_id=user_id,
        conversation_id=conversation_id,
        generation_status="running",
        input_data=input_data,
    )
    session.add(result)
    session.flush()
    return result


def set_task_result_status(
    session: Session,
    task_result_id: int,
    *,
    status: str,
    result_data: dict[str, Any] | None = None,
) -> bool:
    statement = (
        update(ImageTaskResult)
        .where(ImageTaskResult.task_result_id == task_result_id)
        .values(generation_status=status, result_data=result_data)
    )
    return session.execute(statement).rowcount == 1


def link_result_message(session: Session, task_result_id: int, message_id: int) -> bool:
    statement = (
        update(ImageTaskResult)
        .where(ImageTaskResult.task_result_id == task_result_id)
        .values(message_id=message_id)
    )
    return session.execute(statement).rowcount == 1


def get_user_task_result(
    session: Session,
    user_id: int,
    task_result_id: int,
) -> ImageTaskResult | None:
    return session.scalar(
        select(ImageTaskResult).where(
            ImageTaskResult.task_result_id == task_result_id,
            ImageTaskResult.user_id == user_id,
        )
    )
