"""执行数字人专属图并实现共享 AgentRuntime 调用协议。"""

import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
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
from app.agent.runtime.protocol import AgentRuntime
from app.agent.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStreamEvent,
    AgentStreamResult,
    AgentTextDelta,
    QuestionPayload,
)
from app.modules.digital_human.agent.graph import (
    DIGITAL_HUMAN_AGENT_CODE,
    MAX_INPUT_CHARS,
    RECURSION_LIMIT,
    create_digital_human_graph,
)
from app.modules.digital_human.agent.nodes.tool import ASK_USER_QUESTIONS_TOOL_NAME
from app.modules.digital_human.agent.prompts.loader import load_digital_human_prompt
from app.modules.digital_human.agent.state import DigitalHumanState

logger = logging.getLogger(__name__)


class DigitalHumanRuntime(AgentRuntime):
    """以数字人专属图处理输入、流式生成和稳定结果转换。"""

    def __init__(
        self,
        *,
        chat_model: Any,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self._checkpointer = checkpointer
        self._graph: CompiledStateGraph[DigitalHumanState, object, object, object] = (
            create_digital_human_graph(
                chat_model=chat_model,
                checkpointer=checkpointer,
            )
        )
        self._config = BaseAgentConfig(
            system_prompt=load_digital_human_prompt(),
            agent=DIGITAL_HUMAN_AGENT_CODE,
            max_input_chars=MAX_INPUT_CHARS,
            recursion_limit=RECURSION_LIMIT,
        )

    @property
    def compiled_graph(self) -> Any:
        """提供编译后的数字人图供启动检查与诊断。"""

        return self._graph

    async def ainvoke(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AgentResponse:
        normalized_request = self._normalize_request(request)
        graph_config = self._prepare_runnable_config(runnable_config)
        try:
            result = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=normalized_request.message, id=message_id)]},
                config=graph_config,
            )
        except AgentError:
            raise
        except Exception as error:
            logger.warning(
                "digital_human_agent_execution_failed error_type=%s",
                type(error).__name__,
            )
            raise AgentExecutionError(
                "数字人智能体执行失败。", code="agent_execution_failed"
            ) from None
        return self._response_from_result(result)

    async def astream(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        normalized_request = self._normalize_request(request)
        graph_config = self._prepare_runnable_config(runnable_config)
        human_message = HumanMessage(content=normalized_request.message, id=message_id)
        try:
            stream = await self._graph.astream_events(
                {"messages": [human_message]},
                config=graph_config,
                version="v3",
            )
            async with stream:
                async for message in stream.messages:
                    if message.node != "agent_node":
                        continue
                    async for content in message.text:
                        if content:
                            yield AgentTextDelta(content=content)
                result = await stream.output()
            yield AgentStreamResult(response=self._response_from_result(result or {}))
        except AgentError:
            raise
        except Exception as error:
            logger.warning(
                "digital_human_agent_stream_failed error_type=%s",
                type(error).__name__,
            )
            raise AgentExecutionError(
                "数字人智能体执行失败。", code="agent_execution_failed"
            ) from None

    @staticmethod
    def _normalize_request(
        request: AgentRequest | str | Mapping[str, Any],
    ) -> AgentRequest:
        try:
            return (
                request
                if isinstance(request, AgentRequest)
                else AgentRequest.model_validate(
                    {"message": request} if isinstance(request, str) else request
                )
            )
        except ValidationError:
            raise AgentInputError(
                "数字人智能体输入格式无效。", code="invalid_agent_request"
            ) from None

    def _prepare_runnable_config(
        self,
        runnable_config: RunnableConfig | None,
    ) -> RunnableConfig:
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
        metadata.setdefault("agent", DIGITAL_HUMAN_AGENT_CODE)
        prepared["metadata"] = metadata
        return prepared

    @staticmethod
    def _response_from_result(result: Mapping[str, Any]) -> AgentResponse:
        messages = result.get("messages", [])
        last_message = messages[-1] if messages else None
        if (
            isinstance(last_message, ToolMessage)
            and last_message.name == ASK_USER_QUESTIONS_TOOL_NAME
        ):
            try:
                if not isinstance(last_message.content, str):
                    raise ValueError("题卡工具结果必须为 JSON 文本。")
                questions = QuestionPayload.model_validate_json(last_message.content)
            except (ValidationError, ValueError):
                raise AgentExecutionError(
                    "数字人生成的题卡格式无效。",
                    code="invalid_question_tool_result",
                ) from None
            return AgentResponse(
                agent=DIGITAL_HUMAN_AGENT_CODE,
                status="waiting",
                questions=questions,
            )

        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentExecutionError("数字人智能体没有生成有效回答。", code="missing_agent_answer")
        return AgentResponse(
            agent=DIGITAL_HUMAN_AGENT_CODE,
            status="completed",
            answer=answer,
        )
