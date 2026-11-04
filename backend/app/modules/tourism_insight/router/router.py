"""定义文旅洞察文件导入、评论分析和结果查询 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.modules.auth.dependencies import validate_origin
from app.modules.membership.dependencies import require_membership_access
from app.modules.tourism_insight.constants import (
    DEFAULT_COMMENT_IMPORT_LIMIT,
    MAX_FILE_BYTES,
    MAX_IMPORT_ROWS,
)
from app.modules.tourism_insight.dependencies.dependencies import (
    CurrentUser,
    TourismInsightServiceDependency,
)
from app.modules.tourism_insight.errors import TourismInsightValidationError
from app.modules.tourism_insight.schemas.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    CommentPageResponse,
    ImportResponse,
    ResultsResponse,
    SummaryResponse,
)

router = APIRouter(prefix="/tourism-insight", tags=["tourism-insight"])
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


@router.post(
    "/rules/import",
    response_model=ImportResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
async def import_rules(
    user: CurrentUser,
    service: TourismInsightServiceDependency,
    file: Annotated[UploadFile, File(description="评分规则 Excel 文件")],
    replace: Annotated[bool, Form(description="确认清除旧匹配结果并替换评分规则")] = False,
) -> ImportResponse:
    """读取并导入评分规则文件。"""
    content = await file.read(MAX_FILE_BYTES + 1)
    await file.close()
    if len(content) > MAX_FILE_BYTES:
        raise TourismInsightValidationError("文件不能超过 10 MiB。")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise TourismInsightValidationError("请上传 .xlsx 格式的评分规则文件。")
    return service.import_rules(user.id, content, replace=replace)


@router.post(
    "/comments/import",
    response_model=ImportResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
async def import_comments(
    user: CurrentUser,
    service: TourismInsightServiceDependency,
    file: Annotated[UploadFile, File(description="UGC 评论 CSV 文件")],
    limit: Annotated[int, Form(ge=1, le=MAX_IMPORT_ROWS)] = DEFAULT_COMMENT_IMPORT_LIMIT,
) -> ImportResponse:
    """读取并导入 UGC 评论 CSV 文件。"""
    content = await file.read(MAX_FILE_BYTES + 1)
    await file.close()
    if len(content) > MAX_FILE_BYTES:
        raise TourismInsightValidationError("文件不能超过 10 MiB。")
    if not (file.filename or "").lower().endswith(".csv"):
        raise TourismInsightValidationError("请上传 .csv 格式的评论文件。")
    return service.import_comments(user.id, content, limit)


@router.get("/summary", response_model=SummaryResponse)
def get_summary(user: CurrentUser, service: TourismInsightServiceDependency) -> SummaryResponse:
    return service.summary(user.id)


@router.get("/comments", response_model=CommentPageResponse)
def list_comments(
    user: CurrentUser,
    service: TourismInsightServiceDependency,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> CommentPageResponse:
    return service.list_comments(user.id, limit=limit, offset=offset)


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
async def analyze_comments(
    payload: AnalysisRequest,
    user: CurrentUser,
    service: TourismInsightServiceDependency,
) -> AnalysisResponse:
    return await service.analyze_comments(user.id, payload.comment_ids)


@router.get("/results", response_model=ResultsResponse)
def list_results(
    user: CurrentUser,
    service: TourismInsightServiceDependency,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> ResultsResponse:
    return service.list_results(user.id, limit=limit, offset=offset)
