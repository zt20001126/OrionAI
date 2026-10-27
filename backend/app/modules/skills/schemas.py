"""定义技能 API 请求和响应 DTO，与 ORM 模型分离。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SkillType = Literal["agent", "tool"]
SkillStatus = Literal["published", "disabled"]


class SkillResponse(BaseModel):
    """技能基础信息及当前用户的添加状态。"""

    id: UUID
    code: str
    name: str
    description: str | None
    type: SkillType
    status: SkillStatus
    created_at: datetime
    is_added: bool


class MySkillResponse(SkillResponse):
    """当前用户已添加的技能，附带关联创建时间。"""

    added_at: datetime


class SkillPageResponse(BaseModel):
    """技能市场分页结果。"""

    items: list[SkillResponse]
    total: int
    page: int
    page_size: int


class MySkillsResponse(BaseModel):
    """当前用户的可用技能列表。"""

    items: list[MySkillResponse]


class AddSkillRequest(BaseModel):
    """添加技能请求。"""

    model_config = ConfigDict(extra="forbid")

    skill_id: UUID = Field(description="技能 UUID。")
