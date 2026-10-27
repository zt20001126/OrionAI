"""验证图片助手图、参数策略、上游和私有结果访问。"""

import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.schemas import AgentRequest
from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.storage.object_storage import ObjectMetadata, StoredObject
from app.modules.agents.image_agent.parameter_policy import extract_image_options
from app.modules.agents.image_agent.runtime.image_agent import ImageAgent
from app.modules.agents.image_agent.schemas import ImageRequestAnalysis
from app.modules.auth.models import User
from app.modules.conversations.models import Conversation
from app.modules.image_generation.models import TaskResult
from app.modules.image_generation.providers.result_downloader import ImageResultDownloader
from app.modules.image_generation.providers.tokenhub_client import (
    TokenHubImageClient,
    TokenHubImageError,
)
from app.modules.image_generation.schemas import ImageGenerationOptions, TokenHubImageResult
from app.modules.image_generation.service import (
    ImageResultUnavailableError,
    ImageTaskResultService,
)
from app.modules.skills.models import Skill

PNG_BYTES = b"\x89PNG\r\n\x1a\nimage"


def test_task_result_model_matches_generic_schema() -> None:
    columns = TaskResult.__table__.columns

    assert set(columns.keys()) == {
        "id",
        "user_id",
        "conversation_id",
        "skill_code",
        "result",
        "created_at",
    }
    assert columns.id.primary_key
    assert columns.id.type.python_type is int
    assert columns.user_id.nullable is False
    assert columns.conversation_id.nullable is True
    assert columns.skill_code.nullable is False
    assert columns.result.nullable is False
    assert {foreign_key.target_fullname for foreign_key in columns.user_id.foreign_keys} == {
        "users.id"
    }
    assert {
        foreign_key.target_fullname for foreign_key in columns.conversation_id.foreign_keys
    } == {"conversations.id"}
    assert {foreign_key.target_fullname for foreign_key in columns.skill_code.foreign_keys} == {
        "skills.code"
    }


class FakeStructuredModel:
    def __init__(self, results: Sequence[ImageRequestAnalysis]) -> None:
        self.results = list(results)
        self.calls: list[Sequence[BaseMessage]] = []

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> ImageRequestAnalysis:
        self.calls.append(messages)
        return self.results.pop(0)


class FakeChatModel:
    def __init__(self, structured_model: FakeStructuredModel) -> None:
        self.structured_model = structured_model

    def with_structured_output(self, _schema: type[object]) -> FakeStructuredModel:
        return self.structured_model


class FakeTaskStore:
    def __init__(self) -> None:
        self.statuses: dict[int, str] = {}
        self.results: dict[int, Any] = {}

    def create_running(self, **kwargs: Any) -> None:
        self.statuses[kwargs["task_result_id"]] = "running"

    def set_status(self, task_result_id: int, *, status: str, result_data: Any = None) -> None:
        self.statuses[task_result_id] = status
        if result_data is not None:
            self.results[task_result_id] = result_data


class FakeImageClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return TokenHubImageResult(
            image_url="https://result-1.myqcloud.com/image.png",
            width=1024,
            height=1024,
            request_id="request-1",
        )


class FakeDownloader:
    async def download(self, _url: str) -> tuple[bytes, str]:
        return PNG_BYTES, "image/png"


class FakeStorage:
    def __init__(self) -> None:
        self.saved: list[tuple[str, bytes, str]] = []

    def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: dict[str, str],
    ) -> ObjectMetadata:
        self.saved.append((key, data, content_type))
        return ObjectMetadata(key=key, content_length=len(data), content_type=content_type)


@pytest.mark.anyio
async def test_image_agent_asks_for_size_then_resumes_and_saves_result() -> None:
    structured_model = FakeStructuredModel(
        [ImageRequestAnalysis(intent="generate_image", image_prompt="白色陶瓷杯，电商主图")]
    )
    image_client = FakeImageClient()
    task_store = FakeTaskStore()
    storage = FakeStorage()
    agent = ImageAgent(
        settings=Settings(),
        chat_model=FakeChatModel(structured_model),  # type: ignore[arg-type]
        checkpointer=MemorySaver(),
        task_store=task_store,  # type: ignore[arg-type]
        tokenhub_client=image_client,  # type: ignore[arg-type]
        result_downloader=FakeDownloader(),  # type: ignore[arg-type]
        storage_factory=lambda: storage,
    )
    config = {
        "configurable": {
            "thread_id": "image-test-thread",
            "user_id": 51,
            "conversation_id": 62,
            "run_id": "73",
        }
    }

    waiting = await agent.ainvoke(
        AgentRequest(message="生成一张白色陶瓷杯主图"), runnable_config=config
    )

    assert waiting.status == "waiting"
    assert waiting.questions is not None
    assert waiting.questions.questions[0].id == "image_size"
    assert image_client.calls == []
    assert len(structured_model.calls) == 1

    resumed_config = {
        "configurable": {
            **config["configurable"],
            "run_id": "74",
            "resume_answers": {"image_size": "1:1 方图（1024×1024）"},
        }
    }
    completed = await agent.ainvoke(
        AgentRequest(
            message="用户已提交以下选择：\n- 请选择本次生成图片的画幅比例。：1:1 方图（1024×1024）"
        ),
        runnable_config=resumed_config,
    )

    assert completed.status == "completed"
    assert completed.image_result_id is not None
    assert len(structured_model.calls) == 1
    assert image_client.calls[0]["options"].size == "1024x1024"
    assert len(storage.saved) == 1
    assert storage.saved[0][1] == PNG_BYTES
    assert task_store.statuses[int(completed.image_result_id)] == "succeeded"
    assert task_store.results[int(completed.image_result_id)] == {
        "object_key": storage.saved[0][0]
    }


@pytest.mark.anyio
async def test_non_generation_question_does_not_call_image_provider() -> None:
    structured_model = FakeStructuredModel(
        [
            ImageRequestAnalysis(
                intent="other",
                reply="我可以根据文字帮你生成商品主图或详情页图片。",
            )
        ]
    )
    image_client = FakeImageClient()
    agent = ImageAgent(
        settings=Settings(),
        chat_model=FakeChatModel(structured_model),  # type: ignore[arg-type]
        checkpointer=MemorySaver(),
        tokenhub_client=image_client,  # type: ignore[arg-type]
        result_downloader=FakeDownloader(),  # type: ignore[arg-type]
        storage_factory=FakeStorage,
    )

    response = await agent.ainvoke(
        AgentRequest(message="图片助手可以做什么？"),
        runnable_config={"configurable": {"thread_id": "image-other"}},
    )

    assert response.status == "completed"
    assert response.image_result_id is None
    assert response.answer == "我可以根据文字帮你生成商品主图或详情页图片。"
    assert image_client.calls == []


def test_image_parameter_policy_extracts_explicit_size_and_seed() -> None:
    options = extract_image_options("生成商品主图，尺寸 1200×1600，seed=42，水印文字：Orion")

    assert options["size"] == "1200x1600"
    assert options["seed"] == 42
    assert options["footnote"] == "Orion"


def test_image_parameters_reject_conflicting_size_and_pixel_level() -> None:
    options = ImageGenerationOptions(size="1024x1024", generate_max_pixels=1_048_576)

    with pytest.raises(ValueError, match="只能选择一项"):
        options.validate_exclusivity()


@pytest.mark.anyio
async def test_tokenhub_client_sends_supported_options_and_parses_result() -> None:
    observed: dict[str, Any] = {}

    async def handle_request(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers["Authorization"]
        observed["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "hy-image-v3.5-preview",
                "request_id": "tokenhub-1",
                "choices": [
                    {
                        "delta": {
                            "image": {"url": "https://result-1.myqcloud.com/a.png", "width": 512}
                        }
                    }
                ],
            },
        )

    client = TokenHubImageClient(
        Settings(tokenhub_api_key="secret", tokenhub_base_url="https://tokenhub.test"),
        transport=httpx.MockTransport(handle_request),
    )
    result = await client.generate(
        prompt="陶瓷杯主图",
        options=ImageGenerationOptions(size="1024x1024", seed=42),
        session_id="conversation-1",
    )

    assert observed["authorization"] == "Bearer secret"
    assert observed["body"]["size"] == "1024x1024"
    assert observed["body"]["seed"] == 42
    assert "reference_images" not in observed["body"]
    assert result.request_id == "tokenhub-1"
    assert result.width == 512


@pytest.mark.anyio
async def test_tokenhub_client_maps_rate_limit_without_exposing_upstream_body() -> None:
    async def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"secret": "raw upstream body"})

    client = TokenHubImageClient(
        Settings(tokenhub_api_key="secret"),
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(TokenHubImageError) as captured:
        await client.generate(
            prompt="陶瓷杯",
            options=ImageGenerationOptions(size="1024x1024"),
            session_id="conversation-1",
        )

    assert captured.value.code == "TOKENHUB_RATE_LIMITED"
    assert "raw upstream body" not in str(captured.value)


@pytest.mark.anyio
async def test_result_downloader_rejects_untrusted_url_and_checks_png() -> None:
    downloader = ImageResultDownloader(timeout_seconds=3, max_bytes=128)

    with pytest.raises(TokenHubImageError, match="无法安全读取"):
        await downloader.download("http://127.0.0.1/image.png")

    async def handle_request(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG_BYTES)

    valid_downloader = ImageResultDownloader(
        timeout_seconds=3,
        max_bytes=128,
        transport=httpx.MockTransport(handle_request),
    )
    data, mime_type = await valid_downloader.download("https://result-1.myqcloud.com/image.png")
    assert data == PNG_BYTES
    assert mime_type == "image/png"


def test_image_result_service_checks_owner_and_generation_status() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(account="owner@example.com", password_hash="hash")
            stranger = User(account="stranger@example.com", password_hash="hash")
            skill = Skill(code="image_agent", name="图片助手", type="agent", status="published")
            session.add_all([user, stranger, skill])
            session.flush()
            conversation = Conversation(user_id=user.id, skill_code=skill.code)
            session.add(conversation)
            session.flush()
            session.add(
                TaskResult(
                    id=1001,
                    user_id=user.id,
                    conversation_id=conversation.id,
                    skill_code=skill.code,
                    result={
                        "generation_status": "succeeded",
                        "result_data": {"object_key": "images/private.png"},
                    },
                )
            )
            session.add(
                TaskResult(
                    id=1002,
                    user_id=user.id,
                    conversation_id=conversation.id,
                    skill_code=skill.code,
                    result={"generation_status": "failed"},
                )
            )
            session.commit()

            class ReadOnlyStorage:
                def get_object(self, key: str, *, max_bytes: int) -> StoredObject:
                    assert key == "images/private.png"
                    assert max_bytes > 0
                    return StoredObject(key=key, data=PNG_BYTES, content_type="image/png")

            service = ImageTaskResultService(
                session=session,
                settings=Settings(image_result_max_bytes=128),
                storage_factory=ReadOnlyStorage,  # type: ignore[arg-type]
            )
            assert service.get_image(user.id, 1001) == (PNG_BYTES, "image/png")
            with pytest.raises(ImageResultUnavailableError):
                service.get_image(stranger.id, 1001)
            with pytest.raises(ImageResultUnavailableError):
                service.get_image(user.id, 1002)

            class UnsupportedTypeStorage:
                def get_object(self, key: str, *, max_bytes: int) -> StoredObject:
                    return StoredObject(
                        key=key,
                        data=PNG_BYTES,
                        content_type="application/octet-stream",
                    )

            unsupported_type_service = ImageTaskResultService(
                session=session,
                settings=Settings(image_result_max_bytes=128),
                storage_factory=UnsupportedTypeStorage,  # type: ignore[arg-type]
            )
            with pytest.raises(ImageResultUnavailableError):
                unsupported_type_service.get_image(user.id, 1001)
    finally:
        engine.dispose()
