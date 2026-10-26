"""定义 Agent Runtime 对外稳定错误，避免泄露模型或工具异常细节。"""


class AgentError(Exception):
    """Agent 错误基类，携带稳定错误码供业务层映射。"""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class AgentConfigurationError(AgentError):
    """Agent 构建配置或 Checkpointer 运行上下文无效。"""


class AgentInputError(AgentError):
    """用户输入不符合基础对话 Agent 的约定。"""


class AgentExecutionError(AgentError):
    """模型、工具或最终输出无法完成本轮对话。"""
