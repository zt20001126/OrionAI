"""校验并暂存简历优化候选，不执行持久化。"""

import json
from datetime import datetime
from typing import Any

from langchain_core.tools import tool

from app.modules.agents.resume_agent.schemas import ResumeOptimizationCandidate
from app.modules.resume.schemas import TiptapDocument


@tool("stage_resume_optimization", args_schema=ResumeOptimizationCandidate)
def stage_resume_optimization(
    scope: str,
    source_updated_at: str,
    patch: dict[str, Any],
) -> str:
    """校验并暂存简历优化候选；此工具不会修改数据库。"""
    try:
        candidate = ResumeOptimizationCandidate(
            scope=scope,
            source_updated_at=source_updated_at,
            patch=patch,
        )
        _validate_candidate(candidate)
        return json.dumps(
            {"success": True, "candidate": candidate.model_dump(mode="json")},
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        return json.dumps(
            {"success": False, "code": "INVALID_RESUME_CANDIDATE"},
            ensure_ascii=False,
        )


def _validate_candidate(candidate: ResumeOptimizationCandidate) -> None:
    """确保候选只修改允许的简历内容，并引用带时区的来源版本。"""
    timestamp = datetime.fromisoformat(candidate.source_updated_at)
    if timestamp.tzinfo is None:
        raise ValueError("候选必须包含简历来源版本")

    allowed = {
        "basic_info": {"basic_info"},
        "skills": {"skills"},
        "works": {"works"},
        "projects": {"projects"},
        "all": {"basic_info", "skills", "works", "projects"},
    }
    if set(candidate.patch) - allowed[candidate.scope]:
        raise ValueError("候选超出允许范围")

    for key, value in candidate.patch.items():
        if key == "basic_info":
            _validate_basic_info(value)
        elif key == "skills":
            TiptapDocument.model_validate(value)
        elif key in {"works", "projects"}:
            _validate_experience_entries(value)


def _validate_basic_info(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"intended_position"}:
        raise ValueError("仅可优化求职意向")
    intended_position = value["intended_position"]
    if not isinstance(intended_position, str) or not intended_position.strip():
        raise ValueError("求职意向不能为空")


def _validate_experience_entries(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("经历候选格式无效")
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"index", "content"}:
            raise ValueError("经历候选只允许修改正文")
        index = entry["index"]
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("经历索引无效")
        TiptapDocument.model_validate(entry["content"])
