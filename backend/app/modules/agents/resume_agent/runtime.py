"""将简历专属 LangGraph 封装为共享 Agent Runtime。"""

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from app.agent.errors import AgentConfigurationError, AgentExecutionError, AgentInputError
from app.agent.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStreamEvent,
    AgentStreamResult,
    AgentTextDelta,
    QuestionPayload,
)
from app.modules.agents.resume_agent.graph import RESUME_AGENT_CODE, build_resume_agent_graph
from app.modules.agents.resume_agent.tool import create_resume_tools
from app.modules.resume.schemas import JobResumeSnapshot

logger = logging.getLogger(__name__)


class ResumeAgent:
    def __init__(
        self,
        *,
        chat_model: BaseChatModel,
        checkpointer: BaseCheckpointSaver[Any] | None,
        resume_reader: Callable[[int], JobResumeSnapshot],
        resume_writer: Callable[[int, dict[str, Any]], str],
    ) -> None:
        self._checkpointer = checkpointer
        self._resume_writer = resume_writer
        self._graph: CompiledStateGraph[Any, Any, Any, Any] = build_resume_agent_graph(
            chat_model=chat_model,
            tools=create_resume_tools(resume_reader),
            resume_writer=resume_writer,
            checkpointer=checkpointer,
        )

    @property
    def compiled_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        return self._graph

    async def ainvoke(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AgentResponse:
        normalized = self._normalize_request(request)
        config = self._prepare_config(runnable_config)
        try:
            result = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=normalized.message, id=message_id)]},
                config=config,
            )
        except AgentInputError:
            raise
        except Exception as error:
            logger.warning("resume_agent_execution_failed error_type=%s", type(error).__name__)
            raise AgentExecutionError(
                "简历助手执行失败，请稍后重试。", code="resume_agent_failed"
            ) from None
        return self._response_from_result(result)

    async def astream(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        normalized = self._normalize_request(request)
        config = self._prepare_config(runnable_config)
        human_message = HumanMessage(content=normalized.message, id=message_id)
        streamed_text = False
        try:
            stream = await self._graph.astream_events(
                {"messages": [human_message]},
                config=config,
                version="v3",
            )
            async with stream:
                async for message in stream.messages:
                    if message.node != "agent_node":
                        continue
                    async for content in message.text:
                        if content:
                            streamed_text = True
                            yield AgentTextDelta(content=content)

                result = await stream.output()

            response = self._response_from_result(result or {})
            # 输入节点直接生成的确认答复不会经过模型节点，保留其单段文本输出。
            if response.status == "completed" and response.answer and not streamed_text:
                yield AgentTextDelta(content=response.answer)
            yield AgentStreamResult(response=response)
        except AgentInputError:
            raise
        except Exception as error:
            logger.warning("resume_agent_execution_failed error_type=%s", type(error).__name__)
            raise AgentExecutionError(
                "简历助手执行失败，请稍后重试。", code="resume_agent_failed"
            ) from None

    @staticmethod
    def _normalize_request(request: AgentRequest | str | Mapping[str, Any]) -> AgentRequest:
        try:
            return (
                request
                if isinstance(request, AgentRequest)
                else AgentRequest.model_validate(
                    {"message": request} if isinstance(request, str) else request
                )
            )
        except ValidationError:
            raise AgentInputError("智能体输入格式无效。", code="invalid_agent_request") from None

    def _prepare_config(self, runnable_config: RunnableConfig | None) -> RunnableConfig:
        prepared: dict[str, Any] = dict(runnable_config or {})
        configurable = dict(prepared.get("configurable") or {})
        if self._checkpointer is not None and not configurable.get("thread_id"):
            raise AgentConfigurationError("缺少会话线程标识。", code="missing_thread_id")
        if self._checkpointer is not None and not configurable.get("user_id"):
            raise AgentConfigurationError("缺少当前用户标识。", code="missing_user_id")
        prepared["configurable"] = configurable
        prepared.setdefault("recursion_limit", 24)
        metadata = dict(prepared.get("metadata") or {})
        metadata.setdefault("agent", RESUME_AGENT_CODE)
        prepared["metadata"] = metadata
        return prepared

    @staticmethod
    def _response_from_result(result: Mapping[str, Any]) -> AgentResponse:
        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        if isinstance(last, ToolMessage) and last.name == "ask_user_questions":
            try:
                if not isinstance(last.content, str):
                    raise ValueError
                questions = QuestionPayload.model_validate_json(last.content)
            except (ValidationError, ValueError):
                raise AgentExecutionError(
                    "题卡格式无效。", code="invalid_question_result"
                ) from None
            return AgentResponse(agent=RESUME_AGENT_CODE, status="waiting", questions=questions)
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentExecutionError("简历助手没有返回有效回答。", code="missing_resume_answer")
        return AgentResponse(agent=RESUME_AGENT_CODE, status="completed", answer=answer)
