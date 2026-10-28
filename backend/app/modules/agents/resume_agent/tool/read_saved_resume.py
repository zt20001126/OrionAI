"""读取当前用户已保存简历中可用于求职的事实。"""

import json
from collections.abc import Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from app.modules.agents.resume_agent.tool.common import (
    RESUME_UNAVAILABLE_ERROR,
    get_user_id,
)
from app.modules.resume.schemas import JobResumeSnapshot


def create_read_saved_resume_tool(
    reader: Callable[[int], JobResumeSnapshot],
) -> BaseTool:
    """构造绑定简历读取器的简历读取工具。"""

    @tool("read_saved_resume")
    def read_saved_resume(config: RunnableConfig) -> str:
        """读取已保存简历的职业事实，不返回联系方式、年龄或照片。"""
        user_id = get_user_id(config)
        if user_id is None:
            return json.dumps(RESUME_UNAVAILABLE_ERROR, ensure_ascii=False)
        result = reader(user_id)
        return json.dumps(
            {"success": result.status != "unavailable", "data": result.model_dump(mode="json")},
            ensure_ascii=False,
        )

    return read_saved_resume
