"""简历工具共享的用户身份校验和错误响应。"""

from typing import Any

from langchain_core.runnables import RunnableConfig

RESUME_UNAVAILABLE_ERROR = {
    "success": False,
    "code": "RESUME_UNAVAILABLE",
    "message": "当前账号简历不可用。",
}


def get_user_id(config: RunnableConfig) -> int | None:
    """从 LangChain 运行配置中读取有效的当前用户 ID。"""
    configurable: dict[str, Any] = dict((config or {}).get("configurable") or {})
    value = configurable.get("user_id")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None
