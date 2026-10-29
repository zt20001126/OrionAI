"""创建 OpenAI-compatible 对话模型，集中处理 Provider 配置和错误边界。"""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import Settings


class ModelProviderError(Exception):
    """模型 Provider 缺少有效配置或无法创建模型时抛出。"""


class OpenAICompatibleChatModelProvider:
    """使用默认 DeepSeek 或显式 OpenAI-compatible 配置创建对话模型。"""

    def __init__(
        self,
        settings: Settings,
        *,
        api_key: SecretStr | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        provider_name: str = "DeepSeek",
    ) -> None:
        self._settings = settings
        self._api_key = api_key if api_key is not None else settings.deepseek_api_key
        self._base_url = base_url if base_url is not None else settings.deepseek_base_url
        self._model_name = model_name if model_name is not None else settings.deepseek_model
        self._provider_name = provider_name

    def create_chat_model(self) -> BaseChatModel:
        """按需创建模型；此方法只构造客户端，不发起外部请求。"""

        api_key = self._api_key.get_secret_value().strip()
        base_url = self._base_url.strip()
        model_name = self._model_name.strip()
        if not api_key or not base_url or not model_name:
            raise ModelProviderError(f"{self._provider_name} 对话模型配置不完整。")

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            timeout=self._settings.deepseek_timeout_seconds,
            temperature=self._settings.deepseek_temperature,
            max_retries=self._settings.deepseek_max_retries,
        )
