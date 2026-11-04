"""定义文旅洞察 API 请求和响应的数据契约。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.tourism_insight.constants import MAX_ANALYSIS_BATCH_SIZE

SnowflakeId = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,20}$")]


class ImportResponse(BaseModel):
    """文件导入操作的统计和错误摘要。"""

    imported_count: int = Field(description="成功导入记录数")
    skipped_count: int = Field(description="跳过记录数")
    failed_count: int = Field(description="失败记录数")
    errors: list[str] = Field(description="有限数量的行级错误摘要")


class SummaryResponse(BaseModel):
    """当前用户文旅数据的概览。"""

    rules_count: int = Field(description="当前有效评分子项数")
    comments_count: int = Field(description="评论总数")
    analyzed_count: int = Field(description="已有分析结果的评论数")
    rules_ready: bool = Field(description="是否已导入有效评分规则")


class CommentResponse(BaseModel):
    """评论列表展示字段，不包含 ORM 内部状态。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="评论十进制 ID")
    source_type: str = Field(description="csv 或 manual")
    nickname: str | None = Field(description="用户昵称")
    ugc_type: str | None = Field(description="内容类型")
    platform: str | None = Field(description="平台来源")
    title: str | None = Field(description="评论标题")
    content: str = Field(description="评论原文")
    published_at: datetime | None = Field(description="发布时间")
    analyzed: bool = Field(description="是否已有分析结果")


class CommentPageResponse(BaseModel):
    """评论分页响应。"""

    items: list[CommentResponse] = Field(description="评论列表")
    limit: int = Field(description="本页条数")
    offset: int = Field(description="分页偏移量")
    total_count: int = Field(description="评论总数")


class AnalysisRequest(BaseModel):
    """请求分析已导入评论。"""

    comment_ids: list[SnowflakeId] = Field(
        min_length=1,
        max_length=MAX_ANALYSIS_BATCH_SIZE,
        description="需要分析的评论 ID",
    )


class AnalysisItemResponse(BaseModel):
    """单条评论分析执行结果。"""

    comment_id: str = Field(description="评论 ID")
    status: Literal["completed", "failed"] = Field(description="分析执行状态")
    message: str = Field(description="执行结果说明")


class AnalysisResponse(BaseModel):
    """批量评论分析响应。"""

    items: list[AnalysisItemResponse] = Field(description="逐条执行结果")


class MatchRuleResponse(BaseModel):
    """服务端补齐的评分规则层级。"""

    id: str = Field(description="评分规则 ID")
    major_item: str = Field(description="评分大项")
    minor_item: str = Field(description="评分分项")
    indicator_code: str = Field(description="指标编号")
    indicator_name: str = Field(description="指标名称")
    subitem_number: str = Field(description="子项序号")
    subitem_name: str = Field(description="子项名称")
    scoring_criterion: str = Field(description="国标评分口径原文")
    description: str | None = Field(description="规则说明")
    data_source_detail: str | None = Field(description="适用数据源")


class MatchResponse(BaseModel):
    """单条评论与评分子项的匹配证据。"""

    status: Literal["matched", "review", "unmatched"] = Field(description="匹配状态")
    evidence: str | None = Field(description="原文证据片段")
    reason: str | None = Field(description="匹配依据")
    rule: MatchRuleResponse | None = Field(description="服务端读取的真实评分规则")


class ResultGroupResponse(BaseModel):
    """按评论分组的持久匹配结果。"""

    comment: CommentResponse = Field(description="原始评论信息")
    matches: list[MatchResponse] = Field(description="匹配结果列表")


class ResultsResponse(BaseModel):
    """分析结果分页响应。"""

    items: list[ResultGroupResponse] = Field(description="评论分组的分析结果")
    limit: int = Field(description="本页条数")
    offset: int = Field(description="分页偏移量")
