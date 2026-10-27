"""提供登录后读取本人图片任务结果的私有接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.modules.agents.image_agent.dependencies import ImageTaskResultServiceDependency
from app.modules.agents.image_agent.service import ImageResultUnavailableError
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User

router = APIRouter(prefix="/v1/task-results", tags=["task-results"])
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/{task_result_id}/image")
def get_task_result_image(
    task_result_id: int,
    user: CurrentUser,
    service: ImageTaskResultServiceDependency,
) -> Response:
    """只向任务所属用户返回完成状态的图片字节。"""
    try:
        data, content_type = service.get_image(user.id, task_result_id)
    except ImageResultUnavailableError:
        raise HTTPException(status_code=404, detail="图片结果不存在或暂不可用。") from None
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
