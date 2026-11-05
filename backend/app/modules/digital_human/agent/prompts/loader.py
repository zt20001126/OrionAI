"""加载并组合数字人助手身份与行为提示词。"""

from pathlib import Path

_PROMPT_DIRECTORY = Path(__file__).parent


def load_digital_human_prompt() -> str:
    """按通用对话助手结构组合 system 与 agent 提示词。"""

    system_prompt = (_PROMPT_DIRECTORY / "system.md").read_text(encoding="utf-8").strip()
    agent_instructions = (_PROMPT_DIRECTORY / "agent.md").read_text(encoding="utf-8").strip()
    return f"{system_prompt}\n\n{agent_instructions}\n"
