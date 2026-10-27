from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.config import BASIC_CONVERSATION_AGENT
from app.agent.schemas import AgentResponse, Question, QuestionOption, QuestionPayload
from app.core.application import create_app
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.conversations.models import Conversation
from app.modules.skills.models import Skill, UserSkill


class ScriptedAgent:
    """以固定 Agent 响应验证 Service 和 HTTP 持久化边界。"""

    def __init__(self, responses: list[AgentResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(
        self,
        request: object,
        *,
        runnable_config: dict[str, Any],
        message_id: str | None,
    ) -> AgentResponse:
        self.calls.append(
            {
                "request": request,
                "runnable_config": runnable_config,
                "message_id": message_id,
            }
        )
        return self.responses.pop(0)


class FixedTitleGenerator:
    """提供可控标题结果，并记录实际触发的首条消息。"""

    def __init__(self, result: str | None | Exception = "自动生成的标题") -> None:
        self.result = result
        self.messages: list[str] = []

    async def generate_title(self, first_user_message: str) -> str | None:
        self.messages.append(first_user_message)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@asynccontextmanager
async def _test_lifespan(_application: FastAPI):
    """对话 API 测试不连接真实 Checkpointer 或模型。"""

    yield


@pytest.fixture
def conversation_client() -> Iterator[
    tuple[
        TestClient,
        dict[str, User],
        ScriptedAgent,
        FixedTitleGenerator,
        sessionmaker[Session],
    ]
]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as session:
        owner = User(account="owner@example.com", password_hash="hash")
        other_user = User(account="other@example.com", password_hash="hash")
        session.add_all([owner, other_user])
        session.commit()
        session.refresh(owner)
        session.refresh(other_user)
        general_chat = Skill(
            code="general_chat",
            name="通用对话助手",
            description="支持日常问答和多轮对话",
            type="agent",
            status="published",
        )
        session.add(general_chat)
        session.flush()
        session.add_all(
            [
                UserSkill(user_id=owner.id, skill_id=general_chat.id),
                UserSkill(user_id=other_user.id, skill_id=general_chat.id),
            ]
        )
        session.commit()
        session.refresh(owner)
        session.refresh(other_user)

    users = {"current": owner, "other": other_user}
    agent = ScriptedAgent(
        [
            AgentResponse(
                agent=BASIC_CONVERSATION_AGENT,
                status="completed",
                answer="你好，我可以帮助你。",
            ),
            AgentResponse(
                agent=BASIC_CONVERSATION_AGENT,
                status="waiting",
                questions=QuestionPayload(
                    questions=[
                        Question(
                            id="style",
                            title="希望采用哪种表达风格？",
                            type="SingleChoice",
                            options=[
                                QuestionOption(label=label, description=f"选择{label}")
                                for label in ["简洁", "详细", "正式", "轻松"]
                            ],
                            allow_custom_input=False,
                        )
                    ]
                ),
            ),
            AgentResponse(
                agent=BASIC_CONVERSATION_AGENT,
                status="completed",
                answer="我会采用简洁风格。",
            ),
        ]
    )
    title_generator = FixedTitleGenerator()
    test_app = create_app(lifespan=_test_lifespan)

    def override_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_current_user() -> User:
        return users["current"]

    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.state.conversation_agent = agent
    test_app.state.conversation_title_generator = title_generator
    try:
        with TestClient(test_app) as client:
            yield client, users, agent, title_generator, session_factory
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_conversation_endpoints_require_login() -> None:
    with TestClient(create_app(lifespan=_test_lifespan)) as client:
        response = client.get("/api/conversations")

    assert response.status_code == 401


def test_chat_requires_general_chat_to_be_added_before_use(
    conversation_client: tuple[
        TestClient,
        dict[str, User],
        ScriptedAgent,
        FixedTitleGenerator,
        sessionmaker[Session],
    ],
) -> None:
    client, users, agent, title_generator, session_factory = conversation_client
    with session_factory() as session:
        skill_id = session.scalar(select(Skill.id).where(Skill.code == "general_chat"))
        assert skill_id is not None
        session.execute(
            delete(UserSkill).where(
                UserSkill.user_id == users["current"].id,
                UserSkill.skill_id == skill_id,
            )
        )
        session.commit()

    conversation_id = client.post("/api/conversations").json()["id"]
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "你好"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "请先将通用对话助手添加到我的技能后再使用。"
    assert agent.calls == []
    assert title_generator.messages == []


def test_chat_persists_messages_and_resumes_waiting_questions(
    conversation_client: tuple[
        TestClient,
        dict[str, User],
        ScriptedAgent,
        FixedTitleGenerator,
        sessionmaker[Session],
    ],
) -> None:
    client, users, agent, title_generator, _session_factory = conversation_client
    created = client.post("/api/conversations")
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    first_turn = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "你好"},
    )
    assert first_turn.status_code == 200
    assert first_turn.json()["status"] == "completed"
    assert first_turn.json()["message"]["content"] == {
        "parts": [{"type": "text", "text": "你好，我可以帮助你。"}]
    }

    waiting_turn = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "帮我写一份说明"},
    )
    assert waiting_turn.status_code == 200
    assert waiting_turn.json()["status"] == "waiting"
    assert waiting_turn.json()["message"]["content"]["parts"][0]["type"] == "question"
    blocked_message = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "先继续说"},
    )
    assert blocked_message.status_code == 409

    invalid_answer = client.post(
        f"/api/conversations/{conversation_id}/answers",
        json={"answers": {"style": "不存在的选项"}},
    )
    assert invalid_answer.status_code == 422

    resumed_turn = client.post(
        f"/api/conversations/{conversation_id}/answers",
        json={"answers": {"style": "简洁"}},
    )
    assert resumed_turn.status_code == 200
    assert resumed_turn.json()["status"] == "completed"
    assert agent.calls[1]["runnable_config"] == agent.calls[2]["runnable_config"]
    assert title_generator.messages == ["你好"]

    messages = client.get(f"/api/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    items = messages.json()["items"]
    assert [item["role"] for item in items] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert items[2]["content"] == {"parts": [{"type": "text", "text": "帮我写一份说明"}]}
    assert items[4]["content"]["parts"][0]["text"].endswith("简洁")
    listed_conversation = client.get("/api/conversations").json()["items"][0]
    assert listed_conversation["id"] == conversation_id
    assert listed_conversation["title"] == "自动生成的标题"
    assert users["other"].id != users["current"].id


def test_title_failure_falls_back_to_first_user_message(
    conversation_client: tuple[
        TestClient,
        dict[str, User],
        ScriptedAgent,
        FixedTitleGenerator,
        sessionmaker[Session],
    ],
) -> None:
    client, _users, _agent, title_generator, _session_factory = conversation_client
    title_generator.result = None
    conversation_id = client.post("/api/conversations").json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "  生成   会话标题  "},
    )

    assert response.status_code == 200
    assert client.get("/api/conversations").json()["items"][0]["title"] == "生成 会话标题"


def test_existing_messages_with_empty_title_are_not_renamed_from_later_message(
    conversation_client: tuple[
        TestClient,
        dict[str, User],
        ScriptedAgent,
        FixedTitleGenerator,
        sessionmaker[Session],
    ],
) -> None:
    client, _users, _agent, title_generator, session_factory = conversation_client
    conversation_id = client.post("/api/conversations").json()["id"]
    first_response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "原始首条消息"},
    )
    assert first_response.status_code == 200

    with session_factory() as session:
        conversation = session.scalar(
            select(Conversation).where(Conversation.id == int(conversation_id))
        )
        assert conversation is not None
        conversation.title = None
        session.commit()

    later_response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "后续消息不应用作标题来源"},
    )

    assert later_response.status_code == 200
    assert title_generator.messages == ["原始首条消息"]
    assert client.get("/api/conversations").json()["items"][0]["title"] is None


def test_conversation_is_hidden_from_other_users(
    conversation_client: tuple[
        TestClient,
        dict[str, User],
        ScriptedAgent,
        FixedTitleGenerator,
        sessionmaker[Session],
    ],
) -> None:
    client, users, _agent, _title_generator, _session_factory = conversation_client
    conversation = client.post("/api/conversations").json()
    users["current"] = users["other"]

    response = client.get(f"/api/conversations/{conversation['id']}/messages")

    assert response.status_code == 404
