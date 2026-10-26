import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.llm.provider import ModelProviderError, OpenAICompatibleChatModelProvider


def test_provider_uses_deepseek_settings_without_network_request() -> None:
    settings = Settings(
        deepseek_api_key=SecretStr("test-only-key"),
        deepseek_base_url="https://example.invalid/v1",
        deepseek_model="test-model",
        deepseek_temperature=0.2,
        deepseek_timeout_seconds=12.0,
        deepseek_max_retries=1,
    )

    model = OpenAICompatibleChatModelProvider(settings).create_chat_model()

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "test-model"
    assert "test-only-key" not in repr(settings)


def test_provider_rejects_missing_api_key_or_model() -> None:
    provider = OpenAICompatibleChatModelProvider(
        Settings(deepseek_api_key=SecretStr(""), deepseek_model="")
    )

    with pytest.raises(ModelProviderError):
        provider.create_chat_model()
