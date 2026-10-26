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

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
