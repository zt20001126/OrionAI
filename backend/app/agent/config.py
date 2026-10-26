"""定义基础对话 Agent 的身份、输入边界和图执行限制。"""

from dataclasses import dataclass

BASIC_CONVERSATION_AGENT = "basic_conversation_agent"
DEFAULT_MAX_INPUT_CHARS = 20_000
DEFAULT_RECURSION_LIMIT = 24
MAX_QUESTIONS_PER_BATCH = 3
QUESTION_OPTION_COUNT = 4
MAX_QUESTION_ROUNDS_PER_RUN = 3


@dataclass(frozen=True, slots=True)
class BaseAgentConfig:
    """基础对话 Agent 配置；限制单次输入及 LangGraph 节点执行步数。"""

    system_prompt: str
    agent: str = BASIC_CONVERSATION_AGENT
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS
    recursion_limit: int = DEFAULT_RECURSION_LIMIT
