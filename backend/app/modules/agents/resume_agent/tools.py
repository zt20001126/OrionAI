"""创建简历读取、优化候选和岗位方向校验工具。"""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from app.agent.schemas import Question, QuestionOption
from app.modules.agents.resume_agent.schemas import (
    RecommendationRequest,
    ResumeOptimizationCandidate,
)
from app.modules.resume.schemas import (
    JobResumeSnapshot,
    ResumeContent,
    TiptapDocument,
    document_text,
)

_USER_ID_ERROR = {"success": False, "code": "RESUME_UNAVAILABLE", "message": "当前账号简历不可用。"}


def create_resume_tools(
    reader: Callable[[int], JobResumeSnapshot],
) -> list[BaseTool]:
    @tool("read_saved_resume")
    def read_saved_resume(config: RunnableConfig) -> str:
        """读取已保存简历的职业事实，不返回联系方式、年龄或照片。"""
        user_id = _user_id(config)
        if user_id is None:
            return json.dumps(_USER_ID_ERROR, ensure_ascii=False)
        result = reader(user_id)
        return json.dumps(
            {"success": result.status != "unavailable", "data": result.model_dump(mode="json")},
            ensure_ascii=False,
        )

    return [
        read_saved_resume,
        stage_resume_optimization,
        _create_recommend_job_roles_tool(reader),
    ]


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


def _create_recommend_job_roles_tool(reader: Callable[[int], JobResumeSnapshot]) -> BaseTool:
    @tool("recommend_job_roles", args_schema=RecommendationRequest)
    def recommend_job_roles(
        config: RunnableConfig,
        experience_years: int | None = None,
        major: str | None = None,
        skills: str | None = None,
        work_description: str | None = None,
        roles: list[dict[str, Any]] | None = None,
    ) -> str:
        """仅依据当前用户已保存简历中的可验证事实检查岗位方向建议。"""
        try:
            request = RecommendationRequest(
                experience_years=experience_years,
                major=major,
                skills=skills,
                work_description=work_description,
                roles=roles or [],
            )
        except ValueError:
            return json.dumps(
                {"success": False, "status": "no_recommendation"}, ensure_ascii=False
            )

        user_id = _user_id(config)
        if user_id is None:
            return json.dumps(_USER_ID_ERROR, ensure_ascii=False)
        snapshot = reader(user_id)
        if snapshot.status != "found":
            status = "resume_unavailable" if snapshot.status == "unavailable" else "resume_required"
            return json.dumps({"success": False, "status": status}, ensure_ascii=False)

        profile = _verified_profile(snapshot)
        supplied_profile = request.model_dump(exclude={"roles"})
        if not _claims_supported(supplied_profile, profile):
            return json.dumps(
                {"success": False, "status": "invalid_basis"}, ensure_ascii=False
            )

        missing: list[str] = []
        if profile["experience_years"] is None:
            missing.append("工作经验年限")
        if not any(profile[field] for field in ("major", "skills", "work_description")):
            missing.append("专业、技能或相关经历")
        if missing or not request.roles:
            return json.dumps(
                {"success": True, "status": "needs_more_information", "missing": missing},
                ensure_ascii=False,
            )
        for role in request.roles:
            if any(not profile.get(field) for field in role.basis_fields):
                return json.dumps(
                    {"success": False, "status": "invalid_basis"}, ensure_ascii=False
                )
        return json.dumps(
            {
                "success": True,
                "status": "completed",
                "roles": [role.model_dump(mode="json") for role in request.roles],
            },
            ensure_ascii=False,
        )

    return recommend_job_roles


def _verified_profile(snapshot: JobResumeSnapshot) -> dict[str, str | int | None]:
    majors = "\n".join(item.get("major", "") for item in snapshot.educations).strip()
    work_description = "\n".join(
        [item.get("description", "") for item in snapshot.works]
        + [item.get("description", "") for item in snapshot.projects]
    ).strip()
    return {
        "experience_years": snapshot.work_experience_years,
        "major": majors,
        "skills": snapshot.skills.strip(),
        "work_description": work_description,
    }


def _claims_supported(
    claims: dict[str, str | int | None], profile: dict[str, str | int | None]
) -> bool:
    for field, claim in claims.items():
        if claim in (None, ""):
            continue
        evidence = profile.get(field)
        if isinstance(claim, int):
            if claim != evidence:
                return False
        elif not isinstance(evidence, str) or claim.casefold() not in evidence.casefold():
            return False
    return True


def build_optimization_question(candidate: dict[str, Any]) -> Question:
    preview = _candidate_preview(candidate)
    return Question(
        id="resume_optimization",
        title="请预览优化建议，并选择下一步。",
        context=preview,
        type="SingleChoice",
        options=[
            QuestionOption(
                label="确认采用并保存", description="检查简历版本后，将候选内容写入已保存简历。"
            ),
            QuestionOption(label="重新生成候选", description="保留原简历，继续调整优化方向。"),
            QuestionOption(label="取消本次优化", description="不保存本次候选。"),
            QuestionOption(label="暂不处理", description="关闭本次确认，不修改简历。"),
        ],
        allow_custom_input=False,
    )


def _validate_candidate(candidate: ResumeOptimizationCandidate) -> None:
    from datetime import datetime

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
            if not isinstance(value, dict) or set(value) != {"intended_position"}:
                raise ValueError("仅可优化求职意向")
            if (
                not isinstance(value["intended_position"], str)
                or not value["intended_position"].strip()
            ):
                raise ValueError("求职意向不能为空")
        elif key == "skills":
            TiptapDocument.model_validate(value)
        elif key in {"works", "projects"}:
            if not isinstance(value, list) or len(value) > 20:
                raise ValueError("经历候选格式无效")
            for entry in value:
                if not isinstance(entry, dict) or set(entry) != {"index", "content"}:
                    raise ValueError("经历候选只允许修改正文")
                if not isinstance(entry["index"], int) or isinstance(entry["index"], bool):
                    raise ValueError("经历索引无效")
                TiptapDocument.model_validate(entry["content"])


def _candidate_preview(candidate: dict[str, Any]) -> str:
    patch = candidate.get("patch", {})
    changes: list[str] = []
    basic = patch.get("basic_info")
    if isinstance(basic, dict):
        changes.append(f"求职意向：{basic.get('intended_position', '')}")
    if isinstance(patch.get("skills"), dict):
        skills = ResumeContent.model_validate({"skills": patch["skills"]}).skills
        changes.append(f"专业技能：\n{document_text(skills)}")
    for key, label in (("works", "工作经历"), ("projects", "项目经历")):
        entries = patch.get(key)
        if isinstance(entries, list):
            for entry in entries:
                document = TiptapDocument.model_validate(entry["content"])
                changes.append(
                    f"{label}第 {entry['index'] + 1} 项正文：\n{document_text(document)}"
                )
    preview = "本次候选只修改以下职业内容：\n\n" + "\n\n".join(changes)
    if len(preview) > 2_800:
        return preview[:2_780].rstrip() + "\n\n……预览已截断，确认前请继续核对以上内容。"
    return preview


def _user_id(config: RunnableConfig) -> int | None:
    value = dict((config or {}).get("configurable") or {}).get("user_id")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
