"""创建仅能查询可信用户评分规则的 LangChain 工具。"""

from collections.abc import Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class RuleSearchInput(BaseModel):
    """规则检索工具的文本查询参数。"""

    query: str = Field(min_length=1, max_length=1000, description="从游客评价中提取的检索词")


def create_search_rules_tool(
    searcher: Callable[[int, str], list[dict[str, object]]],
    user_id: int,
) -> StructuredTool:
    """通过闭包绑定当前登录用户，避免模型控制数据范围。"""

    def search_rules(query: str) -> list[dict[str, object]]:
        return searcher(user_id, query)

    return StructuredTool.from_function(
        func=search_rules,
        name="search_tourism_rules",
        description="按游客评价语义检索当前用户已导入的评分子项候选。",
        args_schema=RuleSearchInput,
    )
