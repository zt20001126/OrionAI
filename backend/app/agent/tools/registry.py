"""验证并集中管理注入到 Agent 图中的 LangChain 工具。"""

import re
from collections.abc import Iterable

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from app.agent.errors import AgentConfigurationError

_TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ToolRegistry:
    """维护不可变工具集合，并在构建图前校验工具名称和参数模型。"""

    def __init__(self, tools: Iterable[BaseTool] = ()) -> None:
        tool_list = tuple(tools)
        names = [tool.name for tool in tool_list]
        if len(names) != len(set(names)):
            raise AgentConfigurationError("工具名称必须唯一。", code="duplicate_tool_name")

        for tool in tool_list:
            if _TOOL_NAME_PATTERN.fullmatch(tool.name) is None:
                raise AgentConfigurationError(
                    "工具名称必须使用小写字母、数字和下划线。",
                    code="invalid_tool_name",
                )
            if not tool.description.strip():
                raise AgentConfigurationError(
                    "工具必须提供用途描述。", code="missing_tool_description"
                )
            if not isinstance(tool.args_schema, type) or not issubclass(
                tool.args_schema, BaseModel
            ):
                raise AgentConfigurationError(
                    "工具参数必须使用 Pydantic 模型。",
                    code="invalid_tool_schema",
                )

        self._tools = tool_list
        self._names = frozenset(names)

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        """返回只读工具集合，供图节点和模型绑定使用。"""

        return self._tools

    @property
    def names(self) -> frozenset[str]:
        """返回已注册工具名称，用于检查模型发起的工具调用。"""

        return self._names
