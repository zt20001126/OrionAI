from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _normalize_postgres_url_for_runtime(raw_url: str, *, in_container: bool) -> str:
    """容器内将宿主机 localhost 地址改为 Compose PostgreSQL 服务地址。"""

    if not in_container or not raw_url.strip():
        return raw_url
    parsed_url = make_url(raw_url)
    if parsed_url.host not in {"localhost", "127.0.0.1"}:
        return raw_url
    return parsed_url.set(host="postgres", port=5432).render_as_string(hide_password=False)


class Settings(BaseSettings):
    """应用配置，控制 API、Agent、SMTP 和后台提醒 Worker 的运行行为。"""

    app_name: str = "OrionAI"
    environment: str = "development"
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    database_url: str = Field(
        default="postgresql+psycopg://localhost:5432/orionai",
        description="业务数据 PostgreSQL 连接；凭据应通过环境变量配置。",
    )
    checkpoint_database_url: str = Field(
        default="",
        description="LangGraph Checkpointer 专用 PostgreSQL 连接；不得复用业务数据库地址。",
    )
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
    smtp_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=120,
        description="单次 SMTP 连接和发送调用超时；提醒任务租约应大于此值。",
    )
    reminder_task_queue: str = Field(
        default="reminders",
        min_length=1,
        description="Celery 提醒邮件任务队列名称，Worker 应监听此队列。",
    )
    reminder_scan_interval_seconds: int = Field(
        default=30,
        ge=5,
        le=3600,
        description="Celery Beat 扫描到期提醒和待投递执行的间隔秒数。",
    )
    reminder_scan_batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="单次数据库扫描认领的提醒或执行上限。",
    )
    reminder_sending_lease_seconds: int = Field(
        default=120,
        ge=30,
        le=3600,
        description="恢复异常 sending 执行前等待的租约秒数，须大于 SMTP 超时。",
    )
    memory_training_task_queue: str = Field(
        default="memory_training",
        min_length=1,
        description="记忆训练视觉出题 Celery 队列，由共享后台 Worker 监听。",
    )
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
    aliyun_bailian_api_key: SecretStr = Field(
        default=SecretStr(""), description="阿里云百炼 API 密钥，不得写入日志。"
    )
    aliyun_bailian_base_url: str = Field(
        default="", description="阿里云百炼 OpenAI-compatible API 地址。"
    )
    aliyun_bailian_model: str = Field(
        default="qwen3.8-flash", description="记忆训练使用的百炼多模态模型名称。"
    )
    tokenhub_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"),
        description="TokenHub 生图 API 密钥，不得写入日志。",
    )
    tokenhub_base_url: str = Field(
        default="https://tokenhub.tencentmaas.com",
        validation_alias=AliasChoices("TOKENHUB_BASE_URL", "TENCENT_TOKENHUB_BASE_URL"),
        description="TokenHub API 根地址。",
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

    @model_validator(mode="after")
    def validate_and_normalize_runtime_settings(self) -> Settings:
        """校验发送租约并归一化 Compose 容器中的数据库 DSN。"""

        if self.reminder_sending_lease_seconds <= self.smtp_timeout_seconds:
            raise ValueError("提醒发送租约必须长于 SMTP 超时时间。")

        in_container = Path("/.dockerenv").is_file()
        self.database_url = _normalize_postgres_url_for_runtime(
            self.database_url, in_container=in_container
        )
        self.checkpoint_database_url = _normalize_postgres_url_for_runtime(
            self.checkpoint_database_url, in_container=in_container
        )
        return self

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
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
