import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from app.agent.config import BASIC_CONVERSATION_AGENT, BaseAgentConfig
from app.agent.errors import AgentConfigurationError, AgentExecutionError, AgentInputError
from app.agent.runtime.base_agent import BaseAgent, create_basic_conversation_agent
from app.agent.schemas import AgentRequest, AgentResponse, AgentStreamResult, AgentTextDelta
from app.agent.tools.builtin.ask_user_questions import ask_user_questions
from app.agent.tools.registry import ToolRegistry


class ScriptedChatModel(BaseChatModel):
    """依序返回预设模型消息，供 Agent 图单元测试使用。"""

    _responses: list[AIMessage] = PrivateAttr()

    def __init__(self, responses: list[AIMessage]) -> None:
        super().__init__()
        self._responses = responses

    @property
    def _llm_type(self) -> str:
        return "scripted-test-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        if not self._responses:
            raise RuntimeError("No scripted response remains")
        return ChatResult(generations=[ChatGeneration(message=self._responses.pop(0))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        del tools, kwargs
        return self


def _question_tool_call() -> AIMessage:
    return AIMessage(
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


@tool("uppercase_text")
def uppercase_text(text: str) -> str:
    """将输入文本转换为大写。"""

    return text.upper()


@pytest.mark.anyio
async def test_agent_returns_completed_text() -> None:
    agent = BaseAgent(
        config=BaseAgentConfig(system_prompt="请简短回答。"),
        chat_model=ScriptedChatModel([AIMessage(content="你好。")]),
    )

    response = await agent.ainvoke("你好")

    assert response.status == "completed"
    assert response.answer == "你好。"


@pytest.mark.anyio
async def test_agent_streams_text_and_returns_the_same_graph_result() -> None:
    agent = BaseAgent(
        config=BaseAgentConfig(system_prompt="请简短回答。"),
        chat_model=ScriptedChatModel([AIMessage(content="你好。")]),
    )

    events = [event async for event in agent.astream("你好")]

    assert events[0] == AgentTextDelta(content="你好。")
    assert events[-1] == AgentStreamResult(
        response=AgentResponse(
            agent=BASIC_CONVERSATION_AGENT,
            status="completed",
            answer="你好。",
        )
    )
    assert len(events) == 2


@pytest.mark.anyio
async def test_agent_closes_graph_stream_when_consumer_cancels() -> None:
    closed = asyncio.Event()

    class BlockingTextMessage:
        node = "agent_node"

        @property
        def text(self) -> AsyncIterator[str]:
            async def chunks() -> AsyncIterator[str]:
                yield "部分回答"
                await asyncio.Event().wait()

            return chunks()

    class GraphStream:
        async def __aenter__(self) -> "GraphStream":
            return self

        async def __aexit__(self, *_args: object) -> None:
            closed.set()

        @property
        def messages(self) -> AsyncIterator[BlockingTextMessage]:
            async def messages() -> AsyncIterator[BlockingTextMessage]:
                yield BlockingTextMessage()

            return messages()

        async def output(self) -> dict[str, Any]:
            return {}

    class Graph:
        async def astream_events(self, *_args: object, **_kwargs: object) -> GraphStream:
            return GraphStream()

    agent = BaseAgent(
        config=BaseAgentConfig(system_prompt="请简短回答。"),
        chat_model=ScriptedChatModel([]),
    )
    agent._graph = Graph()  # type: ignore[assignment]
    stream = agent.astream("你好")

    assert await anext(stream) == AgentTextDelta(content="部分回答")
    await stream.aclose()

    assert closed.is_set()


@pytest.mark.anyio
async def test_agent_executes_registered_tool_and_returns_model_follow_up() -> None:
    model_tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "uppercase_text",
                "args": {"text": "hello"},
                "id": "call-uppercase-1",
                "type": "tool_call",
            }
        ],
    )
    agent = BaseAgent(
        config=BaseAgentConfig(system_prompt="使用已注册工具处理需要转换的文本。"),
        chat_model=ScriptedChatModel([model_tool_call, AIMessage(content="转换结果：HELLO")]),
        tools=[uppercase_text],
    )

    response = await agent.ainvoke("请转换 hello")

    assert response.status == "completed"
    assert response.answer == "转换结果：HELLO"


@pytest.mark.anyio
async def test_agent_waits_for_question_answers_and_resumes_same_thread() -> None:
    agent = create_basic_conversation_agent(
        chat_model=ScriptedChatModel(
            [_question_tool_call(), AIMessage(content="我会使用短文格式。")]
        ),
        checkpointer=MemorySaver(),
    )
    runnable_config = {"configurable": {"thread_id": "test-user:test-conversation"}}

    waiting_events = [
        event
        async for event in agent.astream(
            "请帮我准备一份内容",
            runnable_config=runnable_config,
            message_id="question-message-1",
        )
    ]
    assert isinstance(waiting_events[-1], AgentStreamResult)
    waiting = waiting_events[-1].response
    assert not any(isinstance(event, AgentTextDelta) for event in waiting_events)
    resumed = await agent.ainvoke(
        AgentRequest(message="用户已选择：短文"),
        runnable_config=runnable_config,
        message_id="answer-message-1",
    )

    assert waiting.status == "waiting"
    assert waiting.questions is not None
    assert waiting.questions.questions[0].id == "format"
    assert resumed.status == "completed"
    assert resumed.answer == "我会使用短文格式。"


@pytest.mark.anyio
async def test_agent_rejects_empty_input_and_redacts_model_error() -> None:
    agent = BaseAgent(
        config=BaseAgentConfig(system_prompt="测试提示词。"),
        chat_model=ScriptedChatModel([]),
    )
    with pytest.raises(AgentInputError):
        await agent.ainvoke("   ")

    failing_agent = BaseAgent(
        config=BaseAgentConfig(system_prompt="测试提示词。"),
        chat_model=ScriptedChatModel([]),
    )
    with pytest.raises(AgentExecutionError) as error:
        await failing_agent.ainvoke("正常输入")
    assert "No scripted response" not in str(error.value)


def test_tool_registry_rejects_duplicate_tools() -> None:
    with pytest.raises(AgentConfigurationError):
        ToolRegistry([ask_user_questions, ask_user_questions])


def test_base_agent_identifier_is_stable() -> None:
    assert BASIC_CONVERSATION_AGENT == "basic_conversation_agent"
