"""将文旅洞察 LangGraph 适配到会话 Agent Runtime 契约。"""

import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from app.agent.errors import AgentExecutionError, AgentInputError
from app.agent.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStreamEvent,
    AgentStreamResult,
    AgentTextDelta,
)
from app.modules.agents.tourism_insight.graph import (
    TOURISM_INSIGHT_CODE,
    build_tourism_insight_graph,
)

logger = logging.getLogger(__name__)


class TourismInsightAgent:
    """支持对话 Runtime 和已保存评论批量分析的文旅智能体。"""

    def __init__(
        self,
        *,
        chat_model: BaseChatModel,
        rule_searcher: Any,
        result_saver: Any,
        checkpointer: BaseCheckpointSaver[Any] | None,
    ) -> None:
        self._checkpointer = checkpointer
        self._graph: CompiledStateGraph[Any, Any, Any, Any] = build_tourism_insight_graph(
            chat_model=chat_model,
            rule_searcher=rule_searcher,
            result_saver=result_saver,
            checkpointer=checkpointer,
        )

    async def ainvoke(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AgentResponse:
        normalized = self._normalize(request)
        config = self._config(runnable_config)
        try:
            result = await self._graph.ainvoke(
                {
                    "messages": [HumanMessage(content=normalized.message, id=message_id)],
                    "analysis_context": {"in_scope": False, "validated_matches": []},
                },
                config=config,
            )
        except AgentInputError:
            raise
        except Exception as error:
            logger.warning("tourism_insight_execution_failed error_type=%s", type(error).__name__)
            raise AgentExecutionError(
                "文旅洞察分析失败，请稍后重试。", code="tourism_insight_failed"
            ) from None
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentExecutionError("文旅洞察未生成有效答复。", code="missing_tourism_answer")
        return AgentResponse(agent=TOURISM_INSIGHT_CODE, status="completed", answer=answer)

    async def astream(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        response = await self.ainvoke(
            request, runnable_config=runnable_config, message_id=message_id
        )
        yield AgentTextDelta(content=response.answer or "")
        yield AgentStreamResult(response=response)

    async def analyze_comment(self, user_id: int, comment_id: int, content: str) -> AgentResponse:
        """通过相同图分析已有评论，使用独立 Checkpointer 线程。"""
        return await self.ainvoke(
            content,
            runnable_config={
                "configurable": {
                    "thread_id": f"tourism:{user_id}:{comment_id}:{uuid4().hex}",
                    "user_id": user_id,
                    "source_comment_id": str(comment_id),
                }
            },
        )

    @staticmethod
    def _normalize(request: AgentRequest | str | Mapping[str, Any]) -> AgentRequest:
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

    def _config(self, runnable_config: RunnableConfig | None) -> RunnableConfig:
        config: dict[str, Any] = dict(runnable_config or {})
        configurable = dict(config.get("configurable") or {})
        if self._checkpointer is not None and not configurable.get("thread_id"):
            raise AgentExecutionError("文旅对话缺少会话上下文。", code="missing_tourism_thread")
        config["configurable"] = configurable
        config.setdefault("recursion_limit", 16)
        metadata = dict(config.get("metadata") or {})
        metadata.setdefault("agent", TOURISM_INSIGHT_CODE)
        config["metadata"] = metadata
        return config
