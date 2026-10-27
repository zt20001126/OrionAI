"""加载并组合基础对话 Agent 的本地提示词文件。"""

from pathlib import Path

_TEMPLATE_DIRECTORY = Path(__file__).parent / "templates"


def load_default_chat_system_prompt() -> str:
    """依次组合助手身份与 Agent 行为约束，保持提示词可独立审阅。"""

    system_prompt = (_TEMPLATE_DIRECTORY / "system.md").read_text(encoding="utf-8").strip()
    agent_instructions = (_TEMPLATE_DIRECTORY / "agent.md").read_text(encoding="utf-8").strip()
    return f"{system_prompt}\n\n{agent_instructions}\n"


def load_conversation_title_prompt() -> str:
    """读取会话标题生成专用提示词。"""

    return (_TEMPLATE_DIRECTORY / "conversation_title.md").read_text(encoding="utf-8").strip()
