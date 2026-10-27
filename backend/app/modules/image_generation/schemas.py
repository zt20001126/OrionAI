"""定义图片生成服务的参数与 TokenHub 响应协议。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImageGenerationOptions(BaseModel):
    """图片生成服务接受的 TokenHub 选项。"""

    model_config = ConfigDict(extra="forbid")

    size: str | None = Field(default=None, max_length=16)
    generate_max_pixels: int | None = None
    seed: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807)
    footnote: str | None = Field(default=None, max_length=16)
    use_search_tool: bool = False

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.lower().split("x")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("图片尺寸必须使用宽x高格式。")
        width, height = (int(part) for part in parts)
        if min(width, height) < 256 or max(width, height) > 8_192 or width * height > 16_777_216:
            raise ValueError("图片宽高或总像素超出允许范围。")
        return f"{width}x{height}"

    @field_validator("generate_max_pixels")
    @classmethod
    def validate_pixel_level(cls, value: int | None) -> int | None:
        if value is not None and value not in {1_048_576, 2_359_296, 4_194_304}:
            raise ValueError("生成面积档位不受支持。")
        return value

    def validate_exclusivity(self) -> "ImageGenerationOptions":
        if self.size is not None and self.generate_max_pixels is not None:
            raise ValueError("精确尺寸和生成面积档位只能选择一项。")
        return self


class TokenHubImageResult(BaseModel):
    """经过校验的 TokenHub 图片地址及诊断元数据。"""

    image_url: str = Field(min_length=1, max_length=4_096)
    width: int | None = Field(default=None, ge=1, le=8_192)
    height: int | None = Field(default=None, ge=1, le=8_192)
    request_id: str | None = Field(default=None, max_length=256)
    provider_model: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)
