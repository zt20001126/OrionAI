"""语音 Provider 可安全向业务层返回的异常。"""


class DigitalHumanProviderError(Exception):
    """百炼语音调用失败、未配置或响应不符合预期。"""
