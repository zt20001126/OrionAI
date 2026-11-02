"""定义需要当前登录用户身份的问题反馈提交 API。"""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import CurrentUser, validate_origin
from app.modules.feedback.dependencies import FeedbackServiceDependency
from app.modules.feedback.errors import (
    FeedbackDeliveryError,
    FeedbackRateLimitError,
    FeedbackUnavailableError,
)
from app.modules.feedback.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackResponse,
    dependencies=[Depends(validate_origin)],
)
def submit_feedback(
    payload: FeedbackRequest,
    user: CurrentUser,
    service: FeedbackServiceDependency,
) -> FeedbackResponse:
    """验证当前会话并将反馈交由业务 Service 处理。"""

    try:
        return service.submit_feedback(user, payload)
    except FeedbackRateLimitError as error:
        raise HTTPException(status_code=429, detail="提交过于频繁，请 60 秒后重试。") from error
    except (FeedbackDeliveryError, FeedbackUnavailableError) as error:
        raise HTTPException(status_code=503, detail="反馈提交失败，请稍后重试。") from error
