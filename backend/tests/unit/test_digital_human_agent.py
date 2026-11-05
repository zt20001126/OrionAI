from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from app.agent.schemas import AgentStreamResult, AgentTextDelta
from app.modules.digital_human.agent.runtime import DigitalHumanRuntime


class ScriptedChatModel(BaseChatModel):
    """为数字人图提供固定回复。"""

    _responses: list[AIMessage] = PrivateAttr()

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
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self._responses.pop(0))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        del tools, kwargs
        return self


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
