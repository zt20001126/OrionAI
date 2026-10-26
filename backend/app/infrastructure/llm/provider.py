"""创建 OpenAI-compatible 对话模型，集中处理 Provider 配置和错误边界。"""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import Settings


class ModelProviderError(Exception):
    """模型 Provider 缺少有效配置或无法创建模型时抛出。"""


class OpenAICompatibleChatModelProvider:
    """使用 Settings 中的 DeepSeek 配置创建 LangChain 对话模型。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_chat_model(self) -> BaseChatModel:
        """按需创建模型；此方法只构造客户端，不发起外部请求。"""

        api_key = self._settings.deepseek_api_key.get_secret_value().strip()
        model_name = self._settings.deepseek_model.strip()
        if not api_key or not model_name:
            raise ModelProviderError("DeepSeek 对话模型配置不完整。")

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=self._settings.deepseek_base_url,
            timeout=self._settings.deepseek_timeout_seconds,
            temperature=self._settings.deepseek_temperature,
            max_retries=self._settings.deepseek_max_retries,
        )
