"""定义登录保护的记忆训练 API，并委托 Service 执行业务。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.modules.auth.dependencies import validate_origin
from app.modules.memory_training.constants import QUESTION_COUNT
from app.modules.memory_training.dependencies import (
    CurrentUser,
    MemoryTrainingServiceDependency,
)
from app.modules.memory_training.errors import MemoryTrainingUnavailableError
from app.modules.memory_training.schemas import (
    AnswerSubmissionRequest,
    ObservationStartedResponse,
    PreparationResponse,
    QuestionsResponse,
    SessionCreatedResponse,
    SessionStatusResponse,
    SubmissionSummaryResponse,
    TrainingResultResponse,
)

router = APIRouter(prefix="/v1/memory-training", tags=["memory-training"])
SessionIdPath = Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")]


@router.get("/prepare", response_model=PreparationResponse)
def get_preparation(
    user: CurrentUser,
    service: MemoryTrainingServiceDependency,
) -> PreparationResponse:
    """返回训练规则，不在准备阶段获取图片。"""

    return service.preparation(user)


@router.post(
    "/sessions",
    response_model=SessionCreatedResponse,
    status_code=201,
    dependencies=[Depends(validate_origin)],
)
def create_training_session(
    user: CurrentUser,
    service: MemoryTrainingServiceDependency,
) -> SessionCreatedResponse:
    """随机抽取一张启用图片并创建短期训练会话。"""

    return service.create_session(user)


@router.post(
    "/sessions/{session_id}/observation/start",
    response_model=ObservationStartedResponse,
    status_code=202,
    dependencies=[Depends(validate_origin)],
)
def start_observation(
    session_id: SessionIdPath,
    user: CurrentUser,
    service: MemoryTrainingServiceDependency,
) -> ObservationStartedResponse:
    """在前端确认图片加载后启动服务端观察计时。"""

    return service.start_observation(user, session_id)


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
def get_training_status(
    session_id: SessionIdPath,
    user: CurrentUser,
    service: MemoryTrainingServiceDependency,
) -> SessionStatusResponse:
    """查询本人会话阶段，以服务端时间推进观察结束状态。"""

    return service.get_status(user, session_id)


@router.get("/sessions/{session_id}/questions", response_model=QuestionsResponse)
def get_training_questions(
    session_id: SessionIdPath,
    user: CurrentUser,
    service: MemoryTrainingServiceDependency,
) -> QuestionsResponse:
    """仅在观察窗口结束且题目生成成功后返回不含答案的题目。"""

    response = service.get_questions(user, session_id)
    if len(response.questions) != QUESTION_COUNT:
        raise MemoryTrainingUnavailableError("当前题目数量无效。")
    return response


@router.post(
    "/sessions/{session_id}/answers",
    response_model=SubmissionSummaryResponse,
    dependencies=[Depends(validate_origin)],
)
def submit_training_answers(
    session_id: SessionIdPath,
    payload: AnswerSubmissionRequest,
    user: CurrentUser,
    service: MemoryTrainingServiceDependency,
) -> SubmissionSummaryResponse:
    """提交全部答案并由后端评分。"""

    return service.submit_answers(user, session_id, payload.answers)


@router.get("/sessions/{session_id}/result", response_model=TrainingResultResponse)
def get_training_result(
    session_id: SessionIdPath,
    user: CurrentUser,
    service: MemoryTrainingServiceDependency,
) -> TrainingResultResponse:
    """读取本人已完成的训练结果和本次原图公开链接。"""

    return service.get_result(user, session_id)
