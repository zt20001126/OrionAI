"""依据当前用户已保存简历校验岗位方向建议。"""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from app.modules.agents.resume_agent.schemas import RecommendationRequest
from app.modules.agents.resume_agent.tool.common import (
    RESUME_UNAVAILABLE_ERROR,
    get_user_id,
)
from app.modules.resume.schemas import JobResumeSnapshot


def create_recommend_job_roles_tool(
    reader: Callable[[int], JobResumeSnapshot],
) -> BaseTool:
    """构造绑定简历读取器的岗位方向建议校验工具。"""

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
            return json.dumps({"success": False, "status": "no_recommendation"}, ensure_ascii=False)

        user_id = get_user_id(config)
        if user_id is None:
            return json.dumps(RESUME_UNAVAILABLE_ERROR, ensure_ascii=False)
        snapshot = reader(user_id)
        if snapshot.status != "found":
            status = "resume_unavailable" if snapshot.status == "unavailable" else "resume_required"
            return json.dumps({"success": False, "status": status}, ensure_ascii=False)

        profile = _verified_profile(snapshot)
        supplied_profile = request.model_dump(exclude={"roles"})
        if not _claims_supported(supplied_profile, profile):
            return json.dumps({"success": False, "status": "invalid_basis"}, ensure_ascii=False)

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
                return json.dumps({"success": False, "status": "invalid_basis"}, ensure_ascii=False)
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
