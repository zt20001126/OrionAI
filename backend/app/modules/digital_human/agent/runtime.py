"""执行数字人专属图并实现共享 AgentRuntime 调用协议。"""

import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

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
from app.agent.nodes.tool import ASK_USER_QUESTIONS_TOOL_NAME
from app.agent.runtime.protocol import AgentRuntime
from app.agent.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStreamEvent,
    AgentStreamResult,
    AgentTextDelta,
    KlineChartPayload,
    PlaceCardsPayload,
    QuestionPayload,
)
from app.modules.digital_human.agent.graph import (
    DIGITAL_HUMAN_AGENT_CODE,
    RECURSION_LIMIT,
    create_digital_human_graph,
)
from app.modules.digital_human.agent.state import DigitalHumanState
from app.modules.resume.schemas import ResumeResponse, ResumeSaveRequest

logger = logging.getLogger(__name__)


class DigitalHumanRuntime(AgentRuntime):
    """以数字人专属图处理输入、流式生成和稳定结果转换。"""

    def __init__(
        self,
        *,
        chat_model: Any,
        resume_reader: Callable[[int], ResumeResponse] | None = None,
        resume_writer: Callable[[int, ResumeSaveRequest], ResumeResponse] | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        """构造数字人图；输入模型、简历读写服务和检查点，供应用生命周期创建。"""
        self._checkpointer = checkpointer
        self._graph: CompiledStateGraph[DigitalHumanState, object, object, object] = (
            create_digital_human_graph(
                chat_model=chat_model,
                resume_reader=resume_reader,
                resume_writer=resume_writer,
                checkpointer=checkpointer,
            )
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
        prepared.setdefault("recursion_limit", RECURSION_LIMIT)
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
            image_result_id=_image_result_id_from_current_turn(messages),
            video_result_id=_video_result_id_from_current_turn(messages),
            kline_chart=_kline_chart_from_current_turn(messages),
            place_cards=_place_cards_from_current_turn(messages),
            route_result=_route_from_current_turn(messages),
        )


def _route_from_current_turn(messages: list[Any]) -> dict[str, Any] | None:
    """提取本轮成功路线工具结果；调用方：数字人运行时。"""
    latest_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        -1,
    )
    for message in reversed(messages[latest_user_index + 1 :]):
        if isinstance(message, ToolMessage) and message.name == "plan_walking_route":
            try:
                result = json.loads(message.content)
            except (ValueError, TypeError):
                return None
            if (
                isinstance(result, dict)
                and result.get("success") is True
                and isinstance(result.get("route"), dict)
            ):
                return result["route"]
            return None
    return None


def _kline_chart_from_current_turn(messages: list[Any]) -> KlineChartPayload | None:
    """提取并校验本轮成功的K线工具结果；调用方：数字人 Runtime。"""
    latest_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        -1,
    )
    for message in reversed(messages[latest_user_index + 1 :]):
        if not isinstance(message, ToolMessage) or message.name != "get_stock_kline":
            continue
        if not isinstance(message.content, str):
            return None
        try:
            result = json.loads(message.content)
        except json.JSONDecodeError:
            return None
        if not isinstance(result, dict) or result.get("status") != "ok":
            return None
        try:
            return KlineChartPayload.model_validate(result["chart"])
        except (ValidationError, KeyError, TypeError):
            raise AgentExecutionError(
                "数字人生成的K线数据格式无效。", code="invalid_kline_tool_result"
            ) from None
    return None


def _place_cards_from_current_turn(messages: list[Any]) -> PlaceCardsPayload | None:
    """提取本轮高德周边搜索结果；供 Runtime 返回结构化商家卡片。"""
    latest_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        -1,
    )
    for message in reversed(messages[latest_user_index + 1 :]):
        if not isinstance(message, ToolMessage) or message.name != "search_nearby_places":
            continue
        if not isinstance(message.content, str):
            return None
        try:
            result = json.loads(message.content)
        except json.JSONDecodeError:
            return None
        if not isinstance(result, dict) or result.get("success") is not True:
            return None
        try:
            return PlaceCardsPayload.model_validate(
                {
                    "title": result["title"],
                    "total": result["total"],
                    "places": [
                        {
                            **{
                                field: place[field]
                                for field in (
                                    "id",
                                    "name",
                                    "address",
                                    "distance",
                                    "tel",
                                    "business_hours",
                                    "rating",
                                    "image_url",
                                )
                            },
                            "location": place.get("location"),
                        }
                        for place in result["pois"]
                    ],
                }
            )
        except (ValidationError, KeyError, TypeError):
            raise AgentExecutionError(
                "数字人生成的周边商家数据格式无效。", code="invalid_place_cards_result"
            ) from None
    return None


def _image_result_id_from_current_turn(messages: list[Any]) -> str | None:
    """读取本轮生图工具成功结果；输入图消息，输出任务 ID；调用方：数字人 Runtime。"""
    latest_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        -1,
    )
    for message in reversed(messages[latest_user_index + 1 :]):
        if not isinstance(message, ToolMessage) or message.name != "generate_image":
            continue
        if not isinstance(message.content, str):
            return None
        try:
            result = json.loads(message.content)
        except json.JSONDecodeError:
            return None
        if not isinstance(result, dict) or result.get("success") is not True:
            return None
        task_result_id = result.get("task_result_id")
        if isinstance(task_result_id, str) and task_result_id.isdigit():
            return task_result_id
        return None
    return None


def _video_result_id_from_current_turn(messages: list[Any]) -> str | None:
    """读取本轮视频工具的成功结果；调用方：数字人 Runtime。"""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage) and message.name == "generate_video":
            if not isinstance(message.content, str):
                return None
            try:
                result = json.loads(message.content)
            except json.JSONDecodeError:
                return None
            if isinstance(result, dict) and result.get("success") is True:
                task_id = result.get("task_result_id")
                if isinstance(task_id, str) and task_id.isdigit():
                    return task_id
            return None
    return None
