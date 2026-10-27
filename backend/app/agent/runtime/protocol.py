"""定义对话服务可调度的 Agent Runtime 契约。"""

from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig

from app.agent.schemas import AgentRequest, AgentResponse, AgentStreamEvent


class AgentRuntime(Protocol):
    """同步会话 API、流式 API 共用的 Agent 执行接口。"""

    async def ainvoke(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AgentResponse: ...

    def astream(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]: ...
