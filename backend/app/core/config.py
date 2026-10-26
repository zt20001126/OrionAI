from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
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
