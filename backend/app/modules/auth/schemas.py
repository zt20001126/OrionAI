import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("请输入有效邮箱地址，长度不能超过 254 个字符。")
        return normalized


class EmailCodeRequest(EmailRequest):
    purpose: Literal["register", "password_reset"]


class RegisterRequest(EmailRequest):
    code: str = Field(pattern=r"^[0-9]{6}$")
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "RegisterRequest":
        if self.password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致。")
        return self


class LoginRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(EmailRequest):
    code: str = Field(pattern=r"^[0-9]{6}$")
    new_password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "PasswordResetRequest":
        if self.new_password != self.password_confirmation:
            raise ValueError("两次输入的密码不一致。")
        return self


class MessageResponse(BaseModel):
    message: str


class AccountResponse(BaseModel):
    account: str


class SessionResponse(BaseModel):
    authenticated: bool
    account: str | None = None
