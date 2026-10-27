"""定义技能 API 请求和响应 DTO，与 ORM 模型分离。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SkillType = Literal["agent", "tool"]
SkillStatus = Literal["published", "disabled"]
MAX_SNOWFLAKE_ID = (1 << 63) - 1
SnowflakeIdString = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,18}$")]


class SkillResponse(BaseModel):
    """技能基础信息及当前用户的添加状态。"""

    id: str = Field(description="Snowflake 技能 ID，以十进制字符串传输。")
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

    skill_id: SnowflakeIdString = Field(description="Snowflake 技能 ID，以十进制字符串传输。")

    @field_validator("skill_id")
    @classmethod
    def validate_snowflake_id_range(cls, skill_id: str) -> str:
        """确保十进制 ID 可以存入有符号 BIGINT。"""

        if int(skill_id) > MAX_SNOWFLAKE_ID:
            raise ValueError("技能 ID 超出 Snowflake ID 范围。")
        return skill_id
