"""简历候选和岗位建议工具的严格输入结构。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResumeOptimizationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["basic_info", "skills", "works", "projects", "all"]
    source_updated_at: str = Field(min_length=1, max_length=64)
    patch: dict[str, Any] = Field(min_length=1)


class RoleRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)
    basis_fields: list[Literal["experience_years", "major", "skills", "work_description"]] = Field(
        min_length=1
    )


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experience_years: int | None = Field(default=None, ge=0, le=80)
    major: str | None = Field(default=None, max_length=300)
    skills: str | None = Field(default=None, max_length=4_000)
    work_description: str | None = Field(default=None, max_length=8_000)
    roles: list[RoleRecommendation] = Field(max_length=3)
