"""使用注入的 ChatModel 和系统提示词生成下一条 AI 消息。"""

import logging
from collections.abc import Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.config import BaseAgentConfig
from app.agent.errors import AgentExecutionError
from app.agent.state import ConversationState
from app.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_agent_node(
    *,
    config: BaseAgentConfig,
    chat_model: BaseChatModel,
    tool_registry: ToolRegistry,
) -> Callable[..., Awaitable[dict[str, list[BaseMessage]]]]:
    """创建模型节点；有工具时才绑定工具，避免无工具模型产生虚假调用。"""

    bound_model = (
        chat_model.bind_tools(list(tool_registry.tools)) if tool_registry.tools else chat_model
    )

    async def agent_node(
        state: ConversationState,
        runnable_config: RunnableConfig | None = None,
    ) -> dict[str, list[BaseMessage]]:
        # 每轮只注入当前系统提示词，避免 Checkpoint 保留旧提示词。
        history = [
            message
            for message in state.get("messages", [])
            if not isinstance(message, SystemMessage)
        ]
        prompt = [SystemMessage(content=config.system_prompt), *history]

        try:
            # Agent 节点是唯一模型调用边界，RunnableConfig 传递限额和运行元数据。
            response = await bound_model.ainvoke(prompt, config=runnable_config)
        except Exception as error:
            logger.warning(
                "agent_model_call_failed agent=%s error_type=%s",
                config.agent,
                type(error).__name__,
            )
            raise AgentExecutionError("模型调用失败。", code="model_call_failed") from None

        if not isinstance(response, AIMessage):
            raise AgentExecutionError("模型返回了不支持的消息类型。", code="invalid_model_response")
        return {"messages": [response]}

    return agent_node
