"""将图片助手专属图封装为通用 Agent Runtime。"""

import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from app.agent.errors import (
    AgentConfigurationError,
    AgentError,
    AgentExecutionError,
    AgentInputError,
)
from app.agent.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStreamEvent,
    AgentStreamResult,
    QuestionPayload,
)
from app.core.config import Settings
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.modules.agents.image_agent.constants import IMAGE_AGENT_CODE
from app.modules.agents.image_agent.graph import build_image_agent_graph
from app.modules.agents.image_agent.tools.generate_image import create_generate_image_tool
from app.modules.image_generation.providers.result_downloader import ImageResultDownloader
from app.modules.image_generation.providers.tokenhub_client import TokenHubImageClient
from app.modules.image_generation.service import TaskResultStore

logger = logging.getLogger(__name__)


class ImageAgent:
    """对齐 BaseAgent 的入参、执行、错误和对外响应契约。"""

    def __init__(
        self,
        *,
        settings: Settings,
        chat_model: BaseChatModel,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        task_store: TaskResultStore | None = None,
        tokenhub_client: TokenHubImageClient | None = None,
        result_downloader: ImageResultDownloader | None = None,
        storage_factory: Any | None = None,
    ) -> None:
        self._checkpointer = checkpointer
        self._task_store = task_store or TaskResultStore()
        self._tokenhub_client = tokenhub_client or TokenHubImageClient(settings)
        self._result_downloader = result_downloader or ImageResultDownloader(
            timeout_seconds=settings.tokenhub_timeout_seconds,
            max_bytes=settings.image_result_max_bytes,
        )
        self._storage_factory = storage_factory or (lambda: AliyunOSSObjectStorage(settings))
        image_tool = create_generate_image_tool(
            settings=settings,
            client=self._tokenhub_client,
            downloader=self._result_downloader,
            task_store=self._task_store,
            storage_factory=self._storage_factory,
        )
        self._graph: CompiledStateGraph[Any, Any, Any, Any] = build_image_agent_graph(
            chat_model=chat_model,
            generate_image_tool=image_tool,
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
        except AgentError:
            raise
        except Exception as error:
            logger.warning("image_agent_execution_failed error_type=%s", type(error).__name__)
            raise AgentExecutionError(
                "图片助手执行失败，请稍后重试。", code="image_agent_failed"
            ) from None
        return self._response_from_result(result)

    async def astream(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
        message_id: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        response = await self.ainvoke(
            request,
            runnable_config=runnable_config,
            message_id=message_id,
        )
        yield AgentStreamResult(response=response)

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
            raise AgentConfigurationError(
                "启用 Checkpointer 时必须提供 configurable.thread_id。",
                code="missing_thread_id",
            )
        prepared["configurable"] = configurable
        prepared.setdefault("recursion_limit", 16)
        metadata = dict(prepared.get("metadata") or {})
        metadata.setdefault("agent", IMAGE_AGENT_CODE)
        prepared["metadata"] = metadata
        return prepared

    @staticmethod
    def _response_from_result(result: Mapping[str, Any]) -> AgentResponse:
        messages = result.get("messages", [])
        last_message = messages[-1] if messages else None
        if isinstance(last_message, ToolMessage) and last_message.name == "ask_user_questions":
            try:
                if not isinstance(last_message.content, str):
                    raise ValueError
                questions = QuestionPayload.model_validate_json(last_message.content)
            except (ValidationError, ValueError):
                raise AgentExecutionError(
                    "图片参数题卡格式无效。", code="invalid_image_question_result"
                ) from None
            return AgentResponse(
                agent=IMAGE_AGENT_CODE,
                status="waiting",
                questions=questions,
            )
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentExecutionError("图片助手未生成有效回答。", code="missing_image_answer")
        result_id = result.get("image_result_id")
        return AgentResponse(
            agent=IMAGE_AGENT_CODE,
            status="completed",
            answer=answer,
            image_result_id=str(result_id) if result_id else None,
        )
