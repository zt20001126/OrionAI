"""定义用户个人资料 API 的请求和响应结构。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.users.constants import MAX_NICKNAME_LENGTH


class UpdateUserProfileRequest(BaseModel):
    """个人资料保存请求；头像文件由同一 multipart 请求单独接收。"""

    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(
        min_length=1,
        max_length=MAX_NICKNAME_LENGTH,
        description="用户昵称，首尾空白会移除，最多 20 个字符",
    )

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_nickname(cls, value: object) -> object:
        """去除昵称首尾空白并拒绝空字符串。"""

        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("昵称不能为空。")
        return normalized


class UserProfileResponse(BaseModel):
    """当前登录用户的个人资料响应，不包含密码或 OSS 对象键。"""

    model_config = ConfigDict(from_attributes=True)

    nickname: str = Field(description="用户昵称；尚未设置时返回账号本地部分")
    account: str = Field(description="规范化后的登录账号，只读")
    avatar_url: str = Field(description="默认头像路径或数据库保存的 OSS 公开访问链接")
    created_at: datetime = Field(description="账号创建时间")
    last_login_at: datetime | None = Field(description="最近一次成功登录时间")
