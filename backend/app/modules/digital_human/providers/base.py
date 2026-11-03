"""百炼 HTTP Provider 共用的配置校验和错误映射。"""

from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.modules.digital_human.providers.errors import DigitalHumanProviderError


def get_bailian_request_context(settings: Settings) -> tuple[str, str]:
    """从已配置的 OpenAI-compatible URL 读取工作空间域名和服务端密钥。"""

    api_key = settings.aliyun_bailian_api_key.get_secret_value().strip()
    try:
        parsed_url = urlsplit(settings.aliyun_bailian_base_url.strip())
    except ValueError:
        raise DigitalHumanProviderError("阿里云百炼语音服务尚未正确配置。") from None
    hostname = (parsed_url.hostname or "").lower()
    if (
        not api_key
        or parsed_url.scheme != "https"
        or not hostname
        or not (hostname.endswith(".maas.aliyuncs.com") or hostname == "dashscope.aliyuncs.com")
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise DigitalHumanProviderError("阿里云百炼语音服务尚未正确配置。")
    return f"{parsed_url.scheme}://{parsed_url.netloc}", api_key


def raise_provider_error(error: Exception) -> DigitalHumanProviderError:
    """统一隐藏上游响应正文和凭据，仅返回稳定错误。"""

    if isinstance(error, httpx.TimeoutException):
        return DigitalHumanProviderError("语音服务响应超时，请稍后重试。")
    if isinstance(error, httpx.HTTPStatusError):
        return DigitalHumanProviderError("阿里云百炼语音服务暂不可用，请稍后重试。")
    return DigitalHumanProviderError("阿里云百炼语音服务暂不可用，请稍后重试。")
