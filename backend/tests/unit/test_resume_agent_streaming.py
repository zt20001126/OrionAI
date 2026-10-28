from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult

from app.agent.schemas import AgentResponse, AgentStreamResult, AgentTextDelta
from app.modules.agents.resume_agent.runtime import ResumeAgent
from app.modules.resume.schemas import JobResumeSnapshot


class UnusedChatModel(BaseChatModel):
    """提供图构造所需的模型接口；本测试用替身图验证流式边界。"""

    @property
    def _llm_type(self) -> str:
        return "unused-test-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        raise AssertionError("此测试不应调用模型。")

    def bind_tools(self, tools: Any, **kwargs: Any) -> "UnusedChatModel":
        del tools, kwargs
        return self


class TextChunkMessage:
    """模拟 Agent 节点按顺序产出的文本片段。"""

    node = "agent_node"

    @property
    def text(self) -> AsyncIterator[str]:
        async def chunks() -> AsyncIterator[str]:
            yield "第一段"
            yield "第二段"

        return chunks()


class GraphStream:
    """模拟 LangGraph 的消息流和最终状态读取接口。"""

    async def __aenter__(self) -> "GraphStream":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    @property
    def messages(self) -> AsyncIterator[TextChunkMessage]:
        async def messages() -> AsyncIterator[TextChunkMessage]:
            yield TextChunkMessage()

        return messages()

    async def output(self) -> dict[str, str]:
        return {"answer": "第一段第二段"}


class GraphWithStreamingOutput:
    """同时提供整段调用和增量调用，以区分运行时实际采用的路径。"""

    async def ainvoke(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"answer": "第一段第二段"}

    async def astream_events(self, *_args: Any, **_kwargs: Any) -> GraphStream:
        return GraphStream()


class GraphStreamWithoutText(GraphStream):
    """模拟由输入节点产生直接答复、没有模型文本节点的流程。"""

    @property
    def messages(self) -> AsyncIterator[TextChunkMessage]:
        async def messages() -> AsyncIterator[TextChunkMessage]:
            if False:
                yield TextChunkMessage()

        return messages()


class GraphWithDirectOutput(GraphWithStreamingOutput):
    async def astream_events(self, *_args: Any, **_kwargs: Any) -> GraphStreamWithoutText:
        return GraphStreamWithoutText()


@pytest.mark.anyio
async def test_resume_agent_emits_graph_text_chunks_before_final_result() -> None:
    agent = ResumeAgent(
        chat_model=UnusedChatModel(),
        checkpointer=None,
        resume_reader=lambda _user_id: JobResumeSnapshot(status="not_found"),
        resume_writer=lambda _user_id, _candidate: "saved",
    )
    agent._graph = GraphWithStreamingOutput()  # type: ignore[assignment]

    events = [event async for event in agent.astream("请给我建议")]

    assert events == [
        AgentTextDelta(content="第一段"),
        AgentTextDelta(content="第二段"),
        AgentStreamResult(
            response=AgentResponse(
                agent="resume_assistant",
                status="completed",
                answer="第一段第二段",
            )
        ),
    ]


@pytest.mark.anyio
async def test_resume_agent_preserves_direct_answers_without_model_text_chunks() -> None:
    agent = ResumeAgent(
        chat_model=UnusedChatModel(),
        checkpointer=None,
        resume_reader=lambda _user_id: JobResumeSnapshot(status="not_found"),
        resume_writer=lambda _user_id, _candidate: "saved",
    )
    agent._graph = GraphWithDirectOutput()  # type: ignore[assignment]

    events = [event async for event in agent.astream("确认保存")]

    assert events == [
        AgentTextDelta(content="第一段第二段"),
        AgentStreamResult(
            response=AgentResponse(
                agent="resume_assistant",
                status="completed",
                answer="第一段第二段",
            )
        ),
    ]
