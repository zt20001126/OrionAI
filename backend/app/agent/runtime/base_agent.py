"""提供 BaseAgent 门面，隔离 LangGraph 状态、工具调用与应用 Service。"""

import logging
from collections.abc import Iterable, Mapping
from functools import partial
from typing import Any

import anyio
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from app.agent.config import BaseAgentConfig
from app.agent.errors import (
    AgentConfigurationError,
    AgentError,
    AgentExecutionError,
    AgentInputError,
)
from app.agent.graph import build_conversation_graph
from app.agent.nodes.tool import ASK_USER_QUESTIONS_TOOL_NAME
from app.agent.prompts.loader import load_default_chat_system_prompt
from app.agent.schemas import AgentRequest, AgentResponse, QuestionPayload
from app.agent.tools.builtin.ask_user_questions import ask_user_questions
from app.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent 对外运行入口；模型、工具和可选 Checkpointer 均由组合层注入。"""

    def __init__(
        self,
        *,
        config: BaseAgentConfig,
        chat_model: BaseChatModel,
        tools: Iterable[BaseTool] = (),
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self._config = config
        self._checkpointer = checkpointer
        self._tool_registry = ToolRegistry(tools)
        self._graph = build_conversation_graph(
            config=config,
            chat_model=chat_model,
            tool_registry=self._tool_registry,
            checkpointer=checkpointer,
        )

    @property
    def compiled_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """返回已编译图，供应用组合层或诊断使用。"""

        return self._graph

    @property
    def tool_registry(self) -> ToolRegistry:
        """返回只读工具注册表，供启动诊断使用。"""

        return self._tool_registry

    async def ainvoke(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AgentResponse:
        """校验文本输入、执行图，并返回不包含 Checkpoint 内部状态的结果。"""

        try:
            normalized_request = (
                request
                if isinstance(request, AgentRequest)
                else AgentRequest.model_validate(
                    {"message": request} if isinstance(request, str) else request
                )
            )
        except ValidationError:
            raise AgentInputError("智能体输入格式无效。", code="invalid_agent_request") from None

        graph_config = self._prepare_runnable_config(runnable_config)
        human_message = HumanMessage(content=normalized_request.message, id=message_id)
        try:
            result = await self._graph.ainvoke(
                {"messages": [human_message]},
                config=graph_config,
            )
        except AgentError:
            raise
        except Exception as error:
            logger.warning(
                "agent_execution_failed agent=%s error_type=%s",
                self._config.agent,
                type(error).__name__,
            )
            raise AgentExecutionError("智能体执行失败。", code="agent_execution_failed") from None

        messages = result.get("messages", [])
        last_message = messages[-1] if messages else None
        if (
            isinstance(last_message, ToolMessage)
            and last_message.name == ASK_USER_QUESTIONS_TOOL_NAME
        ):
            return self._question_response(last_message)

        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentExecutionError("智能体未生成有效回答。", code="missing_agent_answer")
        return AgentResponse(agent=self._config.agent, status="completed", answer=answer)

    def _question_response(self, message: ToolMessage) -> AgentResponse:
        """验证题卡工具输出，再转换为调用方可展示的 waiting 响应。"""

        try:
            if not isinstance(message.content, str):
                raise ValueError("题卡工具结果必须为 JSON 文本。")
            questions = QuestionPayload.model_validate_json(message.content)
        except (ValidationError, ValueError):
            raise AgentExecutionError(
                "智能体生成的题卡格式无效。",
                code="invalid_question_tool_result",
            ) from None
        return AgentResponse(agent=self._config.agent, status="waiting", questions=questions)

    def _prepare_runnable_config(
        self,
        runnable_config: RunnableConfig | None,
    ) -> RunnableConfig:
        """补充执行步数和 Agent 元数据，并校验启用 Checkpointer 的线程 ID。"""

        prepared: dict[str, Any] = dict(runnable_config or {})
        configurable = dict(prepared.get("configurable") or {})
        if self._checkpointer is not None and not configurable.get("thread_id"):
            raise AgentConfigurationError(
                "启用 Checkpointer 时必须提供 configurable.thread_id。",
                code="missing_thread_id",
            )
        if configurable:
            prepared["configurable"] = configurable
        prepared.setdefault("recursion_limit", self._config.recursion_limit)
        metadata = dict(prepared.get("metadata") or {})
        metadata.setdefault("agent", self._config.agent)
        prepared["metadata"] = metadata
        return prepared


def create_basic_conversation_agent(
    *,
    chat_model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[Any],
) -> BaseAgent:
    """创建带题卡工具及 Checkpointer 的基础对话 Agent。"""

    return BaseAgent(
        config=BaseAgentConfig(system_prompt=load_default_chat_system_prompt()),
        chat_model=chat_model,
        tools=[ask_user_questions],
        checkpointer=checkpointer,
    )


def invoke_agent_from_worker_thread(
    agent: BaseAgent,
    request: AgentRequest,
    *,
    runnable_config: RunnableConfig,
    message_id: str,
) -> AgentResponse:
    """从 FastAPI 同步工作线程安全调度异步 Agent，避免阻塞应用事件循环。"""

    invocation = partial(
        agent.ainvoke,
        request,
        runnable_config=runnable_config,
        message_id=message_id,
    )
    return anyio.from_thread.run(invocation)
