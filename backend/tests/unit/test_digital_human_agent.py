from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from app.agent.schemas import AgentStreamResult, AgentTextDelta
from app.agent.tools.registry import ToolRegistry
from app.modules.digital_human.agent import graph
from app.modules.digital_human.agent.capabilities import build_capabilities_prompt
from app.modules.digital_human.agent.runtime import DigitalHumanRuntime
from app.modules.digital_human.agent.tools import current_date, stock_quote


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
async def test_stock_question_continues_to_registered_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question_call = AIMessage(content="", tool_calls=[{
        "name": "ask_user_questions",
        "args": {"questions": [{"id": "stock", "title": "请输入股票名称或代码", "type": "Text"}]},
        "id": "stock-question", "type": "tool_call",
    }])
    stock_call = AIMessage(content="", tool_calls=[{
        "name": "get_stock_quote", "args": {"stock": "600519"},
        "id": "stock-quote", "type": "tool_call",
    }])
    monkeypatch.setattr(
        stock_quote, "_fetch_stock_quote",
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
