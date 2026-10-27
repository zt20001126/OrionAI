"""简历 API 与 Agent 之间使用的结构化数据契约。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_EDUCATIONS = 10
MAX_WORKS = 20
MAX_PROJECTS = 20
MAX_ENTRY_TEXT_CHARS = 4_000
MAX_TOTAL_TEXT_CHARS = 20_000
MAX_JSON_NODES = 2_000
MAX_JSON_BYTES = 256 * 1024
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BasicInfo(StrictModel):
    name: Annotated[str, Field(max_length=80)] = ""
    phone: Annotated[str, Field(max_length=32)] = ""
    email: Annotated[str, Field(max_length=254)] = ""
    intended_position: Annotated[str, Field(max_length=120)] = ""
    work_experience_years: int | None = Field(default=None, ge=0, le=80)
    photo_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None


class EducationItem(StrictModel):
    id: UUID
    school: Annotated[str, Field(min_length=1, max_length=120)]
    major: Annotated[str, Field(max_length=120)] = ""
    degree: Annotated[str, Field(max_length=120)] = ""
    start_month: str
    end_month: str

    @field_validator("start_month", "end_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        if not MONTH_PATTERN.fullmatch(value):
            raise ValueError("月份必须采用 YYYY-MM 格式")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> EducationItem:
        if self.start_month > self.end_month:
            raise ValueError("开始月份不能晚于结束月份")
        return self


class TextNode(StrictModel):
    type: Literal["text"] = "text"
    text: Annotated[str, Field(max_length=MAX_ENTRY_TEXT_CHARS)]


class ParagraphNode(StrictModel):
    type: Literal["paragraph"] = "paragraph"
    content: list[TextNode] = Field(default_factory=list)


class TiptapDocument(StrictModel):
    type: Literal["doc"] = "doc"
    content: list[ParagraphNode] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_text_size(self) -> TiptapDocument:
        if (
            sum(len(node.text) for block in self.content for node in block.content)
            > MAX_ENTRY_TEXT_CHARS
        ):
            raise ValueError("单条简历正文超过字符上限")
        return self


class SkillsDocument(TiptapDocument):
    @model_validator(mode="after")
    def validate_skills_size(self) -> SkillsDocument:
        if sum(len(node.text) for block in self.content for node in block.content) > 10_000:
            raise ValueError("技能正文超过字符上限")
        return self


def empty_skills_document() -> SkillsDocument:
    return SkillsDocument(content=[ParagraphNode()])


class WorkItem(StrictModel):
    id: UUID
    company: Annotated[str, Field(min_length=1, max_length=120)]
    position: Annotated[str, Field(min_length=1, max_length=120)]
    start_month: str
    end_month: str
    content: TiptapDocument

    @field_validator("start_month", "end_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        if not MONTH_PATTERN.fullmatch(value):
            raise ValueError("月份必须采用 YYYY-MM 格式")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> WorkItem:
        if self.start_month > self.end_month:
            raise ValueError("开始月份不能晚于结束月份")
        return self


class ProjectItem(StrictModel):
    id: UUID
    name: Annotated[str, Field(min_length=1, max_length=120)]
    role: Annotated[str, Field(max_length=80)] = ""
    technology_stack: Annotated[str, Field(max_length=240)] = ""
    start_month: str
    end_month: str
    content: TiptapDocument

    @field_validator("start_month", "end_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        if not MONTH_PATTERN.fullmatch(value):
            raise ValueError("月份必须采用 YYYY-MM 格式")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> ProjectItem:
        if self.start_month > self.end_month:
            raise ValueError("开始月份不能晚于结束月份")
        return self


class ResumeContent(StrictModel):
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    educations: list[EducationItem] = Field(default_factory=list, max_length=MAX_EDUCATIONS)
    skills: SkillsDocument = Field(default_factory=empty_skills_document)
    works: list[WorkItem] = Field(default_factory=list, max_length=MAX_WORKS)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=MAX_PROJECTS)

    @model_validator(mode="after")
    def validate_resources(self) -> ResumeContent:
        for field_name in ("educations", "works", "projects"):
            ids = [str(item.id) for item in getattr(self, field_name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{field_name} 中的条目 ID 不能重复")
        data = self.model_dump(mode="json")
        if _count_nodes(data) > MAX_JSON_NODES:
            raise ValueError("简历 JSON 节点数量超过上限")
        if len(str(data).encode("utf-8")) > MAX_JSON_BYTES:
            raise ValueError("简历内容超过大小上限")
        total_chars = sum(
            len(node.text)
            for document in [
                self.skills,
                *(item.content for item in self.works),
                *(item.content for item in self.projects),
            ]
            for block in document.content
            for node in block.content
        )
        if total_chars > MAX_TOTAL_TEXT_CHARS:
            raise ValueError("简历技能、工作和项目正文总量超过上限")
        return self


class PageMargin(StrictModel):
    top: int = Field(default=14, ge=5, le=30)
    right: int = Field(default=14, ge=5, le=30)
    bottom: int = Field(default=14, ge=5, le=30)
    left: int = Field(default=14, ge=5, le=30)


class ResumeStyleConfig(StrictModel):
    font_size_pt: int = Field(default=10, ge=8, le=14)
    line_height: float = Field(default=1.4, ge=1.0, le=2.0)
    section_spacing_pt: int = Field(default=12, ge=4, le=24)
    page_margin_mm: PageMargin = Field(default_factory=PageMargin)
    heading_color: str = Field(default="#2563eb", pattern=r"^#[0-9A-Fa-f]{6}$")


class ResumeSaveRequest(StrictModel):
    content: ResumeContent
    style_config: ResumeStyleConfig
    expected_updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_required_contact(self) -> ResumeSaveRequest:
        info = self.content.basic_info
        if not info.name.strip() or not info.phone.strip():
            raise ValueError("姓名和电话不能为空")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", info.email):
            raise ValueError("邮箱格式不正确")
        return self


class ResumeResponse(StrictModel):
    exists: bool
    content: ResumeContent
    style_config: ResumeStyleConfig
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResumePhotoUploadResponse(StrictModel):
    photo_id: str
    mime_type: Literal["image/png", "image/jpeg"]
    file_size: int = Field(ge=1, le=MAX_PHOTO_BYTES)


class JobResumeSnapshot(StrictModel):
    status: Literal["found", "not_found", "unavailable"]
    updated_at: datetime | None = None
    intended_position: str | None = None
    work_experience_years: int | None = None
    educations: list[dict[str, str]] = Field(default_factory=list)
    skills: str = ""
    works: list[dict[str, str]] = Field(default_factory=list)
    projects: list[dict[str, str]] = Field(default_factory=list)
    truncated: bool = False


def document_text(document: TiptapDocument) -> str:
    return "\n".join("".join(node.text for node in block.content) for block in document.content)


def document_from_text(value: str) -> TiptapDocument:
    return TiptapDocument(
        content=[ParagraphNode(content=[TextNode(text=line)]) for line in value.splitlines()[:100]]
        or [ParagraphNode()]
    )


def _count_nodes(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + sum(_count_nodes(item) for item in value.values())
    if isinstance(value, list):
        return 1 + sum(_count_nodes(item) for item in value)
    return 1
