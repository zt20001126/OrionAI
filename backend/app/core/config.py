from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """应用运行配置，影响 API、认证、对话模型及 Agent 执行边界。"""

    app_name: str = "OrionAI"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    database_url: str = "postgresql+psycopg://orionai:orionai@localhost:5432/orionai"
    redis_url: str = "redis://localhost:6379/0"
    auth_code_pepper: str = ""
    auth_cookie_name: str = "orionai_session"
    auth_session_ttl_seconds: int = Field(default=60 * 60 * 24 * 7, gt=0)
    auth_cookie_secure: bool | None = None
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "OrionAI"
    smtp_use_ssl: bool = True
    aliyun_oss_access_key_id: SecretStr = Field(
        default=SecretStr(""), description="阿里云 OSS AccessKey ID，不得写入日志。"
    )
    aliyun_oss_access_key_secret: SecretStr = Field(
        default=SecretStr(""), description="阿里云 OSS AccessKey Secret，不得写入日志。"
    )
    aliyun_oss_endpoint: str = Field(
        default="", description="阿里云 OSS Bucket 所在地域的 Endpoint。"
    )
    aliyun_oss_bucket: str = Field(default="", description="阿里云 OSS Bucket 名称。")
    aliyun_oss_object_prefix: str = Field(
        default="orionai", description="OrionAI 对象键使用的 OSS 根前缀。"
    )
    deepseek_api_key: SecretStr = Field(
        default=SecretStr(""), description="DeepSeek API 密钥，不得写入日志。"
    )
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com", description="DeepSeek OpenAI-compatible API 地址。"
    )
    deepseek_model: str = Field(default="", description="DeepSeek 对话模型名称。")
    deepseek_timeout_seconds: float = Field(
        default=60.0, gt=0, description="单次模型请求超时时间，单位为秒。"
    )
    deepseek_temperature: float = Field(default=0.7, ge=0, le=2, description="对话模型生成温度。")
    deepseek_max_retries: int = Field(default=2, ge=0, le=5, description="模型请求的最大重试次数。")
    tokenhub_api_key: SecretStr = Field(
        default=SecretStr(""), description="TokenHub 生图 API 密钥，不得写入日志。"
    )
    tokenhub_base_url: str = Field(
        default="https://tokenhub.tencentmaas.com", description="TokenHub API 根地址。"
    )
    tencent_hy_image_model: str = Field(
        default="hy-image-v3.5-preview", description="TokenHub 图片生成模型名称。"
    )
    tencent_hy_image_endpoint: str = Field(
        default="/v1/wand/hunyuan-image/v35-generation", description="TokenHub 图片生成路径。"
    )
    tokenhub_timeout_seconds: float = Field(
        default=180.0, gt=0, le=600, description="TokenHub 请求超时时间，单位为秒。"
    )
    image_result_max_bytes: int = Field(
        default=52_428_800, gt=0, description="单张生成图片最大下载字节数。"
    )
    conversation_title_timeout_seconds: float = Field(
        default=8.0, gt=0, le=60, description="会话标题模型调用时限，单位为秒。"
    )
    snowflake_worker_id: int = Field(
        default=1,
        ge=0,
        le=1022,
        description="Snowflake 节点 ID；同一时刻运行的 backend 实例必须唯一。",
    )

    @field_validator("auth_cookie_secure", mode="before")
    @classmethod
    def empty_cookie_secure_means_automatic(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def aliyun_oss_configured(self) -> bool:
        """判断 OSS 凭据和目标 Bucket 是否齐全；该状态不影响应用启动。"""
        return all(
            (
                self.aliyun_oss_access_key_id.get_secret_value().strip(),
                self.aliyun_oss_access_key_secret.get_secret_value().strip(),
                self.aliyun_oss_endpoint.strip(),
                self.aliyun_oss_bucket.strip(),
            )
        )

    @property
    def tokenhub_configured(self) -> bool:
        """判断图片生成服务是否配置了 API 密钥。"""
        return bool(self.tokenhub_api_key.get_secret_value().strip())

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
