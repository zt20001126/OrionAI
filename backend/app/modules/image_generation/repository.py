"""封装图片助手任务结果的 SQLAlchemy 访问。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.image_generation.models import TaskResult


def create_task_result(
    session: Session,
    *,
    result_id: int,
    user_id: int,
    conversation_id: int | None,
    skill_code: str,
) -> TaskResult:
    """创建生图任务记录并刷新数据库生成的字段。"""
    task_result = TaskResult(
        id=result_id,
        user_id=user_id,
        conversation_id=conversation_id,
        skill_code=skill_code,
        result={"generation_status": "running"},
    )
    session.add(task_result)
    session.flush()
    return task_result


def set_task_result_status(
    session: Session,
    result_id: int,
    *,
    status: str,
    result_data: dict[str, Any] | None = None,
) -> bool:
    """更新生图任务状态及可选结果元数据。"""
    task_result = session.get(TaskResult, result_id)
    if task_result is None:
        return False
    updated_result = dict(task_result.result)
    updated_result["generation_status"] = status
    if result_data is not None:
        updated_result["result_data"] = result_data
    task_result.result = updated_result
    session.flush()
    return True


def get_user_task_result(
    session: Session,
    user_id: int,
    result_id: int,
) -> TaskResult | None:
    """按任务 ID 和用户 ID 查询任务，确保读取范围受用户所有权约束。"""
    return session.scalar(
        select(TaskResult).where(
            TaskResult.id == result_id,
            TaskResult.user_id == user_id,
        )
    )
