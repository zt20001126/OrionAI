from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from app.agent.schemas import AgentStreamResult, AgentTextDelta
from app.agent.tools.registry import ToolRegistry
from app.modules.digital_human.agent import graph
from app.modules.digital_human.agent.capabilities import build_capabilities_prompt
from app.modules.digital_human.agent.runtime import DigitalHumanRuntime
from app.modules.digital_human.agent.tools import (
    current_date,
    index_quote,
    location,
    route_planning,
    stock_kline,
    stock_quote,
)
from app.modules.digital_human.providers.amap import AmapIpLocation, AmapProviderError


class ScriptedChatModel(BaseChatModel):
    """为数字人图提供固定回复。"""

    _responses: list[AIMessage] = PrivateAttr()
    _received_messages: list[BaseMessage] = PrivateAttr(default_factory=list)

    def __init__(self, responses: list[AIMessage]) -> None:
        super().__init__()
        self._responses = responses

    @property
    def _llm_type(self) -> str:
        return "digital-human-test-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._received_messages = messages
        del stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self._responses.pop(0))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        del tools, kwargs
        return self


def test_capabilities_require_all_registered_tools() -> None:
    names = frozenset({"get_current_date", "get_current_weather", "get_stock_quote"})
    prompt = build_capabilities_prompt(names)
    assert "日常交流" in prompt
    assert "日期查询" in prompt
    assert "天气查询" not in prompt
    assert "A 股行情查询" not in prompt

    complete_prompt = build_capabilities_prompt(names | {"ask_user_questions"})
    assert "天气查询" in complete_prompt
    assert "A 股行情查询" in complete_prompt
    assert "互动提问" in complete_prompt
    assert "A 股K线查询" not in complete_prompt
    assert "A 股K线查询" in build_capabilities_prompt(
        names | {"ask_user_questions", "get_stock_kline"}
    )
    route_prompt = build_capabilities_prompt(frozenset({"plan_route", "ask_user_questions"}))
    assert "plan_route.city" in route_prompt
    assert "限定起终点解析范围" in route_prompt
    kline_prompt = build_capabilities_prompt(names | {"ask_user_questions", "get_stock_kline"})
    assert "仅在用户明确要求 MA 或均线时" in kline_prompt
    assert "ma_periods" in kline_prompt
    assert "文字回答中说明所请求周期的最新有效均线值" in kline_prompt


@pytest.mark.anyio
async def test_graph_injects_only_capabilities_backed_by_registered_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def without_weather(tools: Any) -> ToolRegistry:
        return ToolRegistry(tool for tool in tools if tool.name != "get_current_weather")

    monkeypatch.setattr(graph, "ToolRegistry", without_weather)
    model = ScriptedChatModel([AIMessage(content="我可以查询日期。")])
    runtime = DigitalHumanRuntime(chat_model=model)
    await runtime.ainvoke("你能做什么？")

    system_prompt = model._received_messages[0].content
    assert isinstance(system_prompt, str)
    assert "日期查询" in system_prompt
    assert "A 股行情查询" in system_prompt
    assert "天气查询" not in system_prompt
    assert "get_current_weather" not in system_prompt


@pytest.mark.anyio
async def test_digital_human_runtime_uses_its_own_graph_and_checkpointer() -> None:
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel([AIMessage(content="你好，我是数字人助手。")]),
        checkpointer=MemorySaver(),
    )

    response = await runtime.ainvoke(
        "你好",
        runnable_config={"configurable": {"thread_id": "orionai:test:digital_human:1"}},
        message_id="turn-1",
    )

    assert response.agent == "digital_human"
    assert response.answer == "你好，我是数字人助手。"
    assert response.status == "completed"
    assert {"input_node", "agent_node", "tool_node", "output_node"}.issubset(
        runtime.compiled_graph.nodes
    )


@pytest.mark.anyio
async def test_digital_human_runtime_streams_text_and_final_response() -> None:
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel([AIMessage(content="流式数字人回复")]),
    )

    events = [event async for event in runtime.astream("开始对话")]

    assert any(isinstance(event, AgentTextDelta) for event in events)
    assert isinstance(events[-1], AgentStreamResult)
    assert events[-1].response.agent == "digital_human"
    assert events[-1].response.answer == "流式数字人回复"


@pytest.mark.anyio
async def test_digital_human_runtime_uses_shared_question_tool_and_pauses() -> None:
    """确认数字人图复用题卡工具后，仍向会话调用方返回等待状态。"""

    question_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "ask_user_questions",
                "args": {
                    "questions": [
                        {
                            "id": "format",
                            "title": "请选择输出格式",
                            "type": "SingleChoice",
                            "options": [
                                {"label": label, "description": f"采用{label}格式"}
                                for label in ["短文", "清单", "表格", "邮件"]
                            ],
                            "allow_custom_input": False,
                        }
                    ]
                },
                "id": "call-question-1",
                "type": "tool_call",
            }
        ],
    )
    runtime = DigitalHumanRuntime(chat_model=ScriptedChatModel([question_call]))

    response = await runtime.ainvoke("请提供格式选项")

    assert response.agent == "digital_human"
    assert response.status == "waiting"
    assert response.questions is not None
    assert response.questions.questions[0].id == "format"


def test_current_date_uses_beijing_date_across_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 11, 4, 16, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(current_date, "datetime", FixedDatetime)
    assert current_date.get_current_date.invoke({}) == "北京时间：2026-11-05，星期四"


@pytest.mark.anyio
async def test_digital_human_calls_date_tool_and_returns_answer() -> None:
    date_call = AIMessage(
        content="",
        tool_calls=[{"name": "get_current_date", "args": {}, "id": "date-1", "type": "tool_call"}],
    )
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel([date_call, AIMessage(content="这是当前北京时间日期。")]),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "date-test"}}
    response = await runtime.ainvoke("今天几号？", runnable_config=config)
    state = await runtime.compiled_graph.aget_state(config)

    assert response.answer == "这是当前北京时间日期。"
    assert any(
        message.type == "tool" and "北京时间：" in message.content
        for message in state.values["messages"]
    )


@pytest.mark.anyio
async def test_digital_human_location_tool_receives_current_ip_and_returns_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_user_location",
                "args": {},
                "id": "location-1",
                "type": "tool_call",
            }
        ],
    )
    received_ips: list[str | None] = []

    async def locate(_client: object, client_ip: str | None) -> AmapIpLocation:
        received_ips.append(client_ip)
        return AmapIpLocation(province="北京市", city="北京市", adcode="110000")

    monkeypatch.setattr(location.AmapIpLocationClient, "locate", locate)
    model = ScriptedChatModel([tool_call, AIMessage(content="你大致在北京市，位置由 IP 估计。")])
    runtime = DigitalHumanRuntime(chat_model=model, checkpointer=MemorySaver())
    thread_id = "digital-human-location-checkpoint"

    response = await runtime.ainvoke(
        "我现在在哪个城市？",
        runnable_config={"configurable": {"thread_id": thread_id, "client_ip": "114.247.50.2"}},
    )
    state = await runtime.compiled_graph.aget_state({"configurable": {"thread_id": thread_id}})

    assert received_ips == ["114.247.50.2"]
    assert response.answer == "你大致在北京市，位置由 IP 估计。"
    assert any(
        message.type == "tool" and "北京市" in message.content
        for message in model._received_messages
    )
    assert "client_ip" not in state.config["configurable"]
    assert all("114.247.50.2" not in str(message.content) for message in state.values["messages"])


@pytest.mark.anyio
async def test_digital_human_can_answer_when_location_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_user_location",
                "args": {},
                "id": "location-failure-1",
                "type": "tool_call",
            }
        ],
    )

    async def fail_lookup(_client: object, _client_ip: str | None) -> AmapIpLocation:
        raise AmapProviderError("IP 定位请求超时，请稍后重试。")

    monkeypatch.setattr(location.AmapIpLocationClient, "locate", fail_lookup)
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel(
            [tool_call, AIMessage(content="暂时无法根据 IP 判断你所在的城市。")]
        )
    )

    response = await runtime.ainvoke(
        "我现在在哪？",
        runnable_config={"configurable": {"client_ip": "114.247.50.2"}},
    )

    assert response.answer == "暂时无法根据 IP 判断你所在的城市。"


@pytest.mark.anyio
async def test_digital_human_does_not_call_location_tool_for_ordinary_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_location(_client: object, _client_ip: str | None) -> AmapIpLocation:
        pytest.fail("普通聊天不应调用定位工具")

    monkeypatch.setattr(location.AmapIpLocationClient, "locate", unexpected_location)
    runtime = DigitalHumanRuntime(chat_model=ScriptedChatModel([AIMessage(content="你好。")]))

    response = await runtime.ainvoke("你好")

    assert response.answer == "你好。"


@pytest.mark.anyio
async def test_stock_question_continues_to_registered_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "ask_user_questions",
                "args": {
                    "questions": [{"id": "stock", "title": "请输入股票名称或代码", "type": "Text"}]
                },
                "id": "stock-question",
                "type": "tool_call",
            }
        ],
    )
    stock_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_stock_quote",
                "args": {"stock": "600519"},
                "id": "stock-quote",
                "type": "tool_call",
            }
        ],
    )
    monkeypatch.setattr(
        stock_quote,
        "_fetch_stock_quote",
        lambda stock: {"status": "ok", "code": stock, "price": 100},
    )
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel(
            [question_call, stock_call, AIMessage(content="价格为100元。")]
        ),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "stock-test"}}
    question = await runtime.ainvoke("帮我查询股票", runnable_config=config)
    assert question.status == "waiting"
    assert question.questions is not None
    assert question.questions.questions[0].type == "Text"

    response = await runtime.ainvoke("股票：600519", runnable_config=config)
    state = await runtime.compiled_graph.aget_state(config)
    assert response.answer == "价格为100元。"
    assert any(
        message.type == "tool" and message.name == "get_stock_quote" and "600519" in message.content
        for message in state.values["messages"]
    )


@pytest.mark.anyio
async def test_route_mode_question_resumes_and_calls_selected_route_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question_call = _route_mode_question_call()
    route_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "plan_route",
                "args": {
                    "mode": "cycling",
                    "origin": "杭州市西湖区灵隐路",
                    "destination": "杭州西湖",
                },
                "id": "route-plan",
                "type": "tool_call",
            }
        ],
    )

    async def geocode(_self: object, address: str, city: str | None = None):
        del city
        location = "120.150000,30.280000" if "灵隐" in address else "120.160000,30.290000"
        return route_planning.AmapGeocodedLocation(name=address, location=location)

    async def plan(
        _self: object,
        mode: str,
        origin: str,
        destination: str,
        origin_name: str,
        destination_name: str,
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "origin": {"name": origin_name, "location": origin},
            "destination": {"name": destination_name, "location": destination},
            "distance_m": 1200,
            "duration_s": 600,
            "steps": [{"instruction": "沿道路骑行", "distance_m": 1200, "polyline": None}],
        }

    monkeypatch.setattr(route_planning.AmapGeocodingClient, "geocode", geocode)
    monkeypatch.setattr(route_planning.AmapRoutePlanningClient, "plan", plan)
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel(
            [question_call, route_call, AIMessage(content="已规划骑行路线。")]
        ),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "digital-human-route-mode"}}

    question = await runtime.ainvoke(
        "帮我从杭州市西湖区灵隐路到杭州西湖规划路线。", runnable_config=config
    )
    response = await runtime.ainvoke(
        "用户已提交以下选择：\n- 路线方式：骑行", runnable_config=config
    )

    assert question.status == "waiting"
    assert question.questions is not None
    assert [option.label for option in question.questions.questions[0].options] == [
        "步行",
        "骑行",
        "驾车",
        "暂不规划",
    ]
    assert response.answer == "已规划骑行路线。"
    assert response.route_result is not None
    assert response.route_result["mode"] == "cycling"


@pytest.mark.anyio
async def test_explicit_route_mode_calls_route_without_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned_modes: list[str] = []

    async def geocode(_self: object, address: str, city: str | None = None):
        del city
        return route_planning.AmapGeocodedLocation(name=address, location="120.15,30.28")

    async def plan(
        _self: object,
        mode: str,
        origin: str,
        destination: str,
        origin_name: str,
        destination_name: str,
    ) -> dict[str, Any]:
        planned_modes.append(mode)
        return {
            "mode": mode,
            "origin": {"name": origin_name, "location": origin},
            "destination": {"name": destination_name, "location": destination},
            "distance_m": 1000,
            "duration_s": 300,
            "steps": [{"instruction": "沿道路行驶", "distance_m": 1000, "polyline": None}],
        }

    monkeypatch.setattr(route_planning.AmapGeocodingClient, "geocode", geocode)
    monkeypatch.setattr(route_planning.AmapRoutePlanningClient, "plan", plan)
    route_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "plan_route",
                "args": {"mode": "driving", "origin": "杭州西湖", "destination": "灵隐寺"},
                "id": "direct-route-plan",
                "type": "tool_call",
            }
        ],
    )
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel([route_call, AIMessage(content="已规划驾车路线。")]),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "digital-human-explicit-route-mode"}}

    response = await runtime.ainvoke("请从杭州西湖驾车到灵隐寺。", runnable_config=config)
    state = await runtime.compiled_graph.aget_state(config)

    assert response.route_result is not None
    assert response.route_result["mode"] == "driving"
    assert planned_modes == ["driving"]
    assert not any(
        isinstance(message, ToolMessage) and message.name == "ask_user_questions"
        for message in state.values["messages"]
    )


@pytest.mark.anyio
async def test_cancelled_route_mode_does_not_call_route_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned_modes: list[str] = []

    async def plan(
        _self: object,
        mode: str,
        origin: str,
        destination: str,
        origin_name: str,
        destination_name: str,
    ) -> dict[str, Any]:
        planned_modes.append(mode)
        raise AssertionError("取消路线后不应调用路线 Provider")

    monkeypatch.setattr(route_planning.AmapRoutePlanningClient, "plan", plan)
    route_question = _route_mode_question_call()
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel(
            [route_question, AIMessage(content="好的，已取消本次路线规划。")]
        ),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "digital-human-cancel-route"}}

    question = await runtime.ainvoke("帮我规划一条路线。", runnable_config=config)
    response = await runtime.ainvoke(
        "用户已提交以下选择：\n- 路线方式：暂不规划", runnable_config=config
    )
    state = await runtime.compiled_graph.aget_state(config)

    assert question.status == "waiting"
    assert response.status == "completed"
    assert response.route_result is None
    assert planned_modes == []
    assert not any(
        isinstance(message, ToolMessage) and message.name == "plan_route"
        for message in state.values["messages"]
    )


def _route_mode_question_call() -> AIMessage:
    """构造路线方式题卡调用。

    输出：包含三类方式和取消选项的 Tool Call；调用方：数字人路线 Agent 测试。
    """
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "ask_user_questions",
                "args": {
                    "questions": [
                        {
                            "id": "route_mode",
                            "title": "请选择路线方式",
                            "type": "SingleChoice",
                            "options": [
                                {"label": "步行", "description": "规划步行路线"},
                                {"label": "骑行", "description": "规划骑行路线"},
                                {"label": "驾车", "description": "规划驾车路线"},
                                {"label": "暂不规划", "description": "取消本次路线规划"},
                            ],
                            "allow_custom_input": False,
                        }
                    ]
                },
                "id": "route-mode-question",
                "type": "tool_call",
            }
        ],
    )


@pytest.mark.anyio
async def test_stock_kline_tool_result_is_attached_to_agent_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = {
        "code": "600519",
        "name": "贵州茅台",
        "period": "daily",
        "adjust": "qfq",
        "start_date": "2026-11-10",
        "end_date": "2026-11-10",
        "source": "AKShare",
        "candles": [
            {
                "date": "2026-11-10",
                "open": 10,
                "close": 11,
                "high": 12,
                "low": 9,
                "volume": 100,
            }
        ],
        "moving_averages": [{"period": 5, "values": [10.5]}],
    }
    monkeypatch.setattr(
        stock_kline,
        "_query_kline",
        lambda *_args: {"status": "ok", "chart": chart},
    )
    tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_stock_kline",
                "args": {"stock": "600519", "period": "daily"},
                "id": "kline-1",
                "type": "tool_call",
            }
        ],
    )
    runtime = DigitalHumanRuntime(
        chat_model=ScriptedChatModel([tool_call, AIMessage(content="这是近期日K走势。")]),
        checkpointer=MemorySaver(),
    )

    response = await runtime.ainvoke(
        "查询贵州茅台的日K线",
        runnable_config={"configurable": {"thread_id": "kline-test"}},
    )

    assert response.kline_chart is not None
    assert response.kline_chart.code == "600519"
    assert response.kline_chart.candles[0].close == 11
    assert response.kline_chart.moving_averages[0].values == [10.5]


@pytest.mark.anyio
async def test_index_query_reaches_registered_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证指数提问经过数字人图执行指数工具并将结果交回模型。"""
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_index_quote",
                "args": {"index": "上证指数"},
                "id": "index-quote",
                "type": "tool_call",
            }
        ],
    )
    monkeypatch.setattr(
        index_quote,
        "_fetch_index_quote",
        lambda index: {
            "status": "ok",
            "name": index,
            "code": "000001",
            "value": 3000,
        },
    )
    model = ScriptedChatModel([call, AIMessage(content="上证指数为 3000 点。")])
    runtime = DigitalHumanRuntime(chat_model=model, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "index-test"}}
    response = await runtime.ainvoke("上证指数多少点？", runnable_config=config)
    state = await runtime.compiled_graph.aget_state(config)
    assert response.answer == "上证指数为 3000 点。"
    assert "A 股指数行情查询" in model._received_messages[0].content
    assert any(
        message.type == "tool" and message.name == "get_index_quote" and "3000" in message.content
        for message in state.values["messages"]
    )
