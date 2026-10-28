"""组装简历助手使用的独立工具实现。"""

from collections.abc import Callable

from langchain_core.tools import BaseTool

from app.modules.agents.resume_agent.tool.read_saved_resume import (
    create_read_saved_resume_tool,
)
from app.modules.agents.resume_agent.tool.recommend_job_roles import (
    create_recommend_job_roles_tool,
)
from app.modules.agents.resume_agent.tool.stage_resume_optimization import (
    stage_resume_optimization,
)
from app.modules.resume.schemas import JobResumeSnapshot


def create_resume_tools(
    reader: Callable[[int], JobResumeSnapshot],
) -> list[BaseTool]:
    """将简历读取、优化候选和岗位建议工具组装为 Agent 工具列表。"""
    return [
        create_read_saved_resume_tool(reader),
        stage_resume_optimization,
        create_recommend_job_roles_tool(reader),
    ]


__all__ = ["create_resume_tools"]
