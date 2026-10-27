"""加载并组合图片助手身份及业务行为提示词。"""

from pathlib import Path

_TEMPLATE_DIRECTORY = Path(__file__).parent / "templates"


def load_image_agent_prompt() -> str:
    """按通用 Agent 的提示词结构组合 system 与 agent 模板。"""
    system_prompt = (_TEMPLATE_DIRECTORY / "system.md").read_text(encoding="utf-8").strip()
    agent_instructions = (_TEMPLATE_DIRECTORY / "agent.md").read_text(encoding="utf-8").strip()
    return f"{system_prompt}\n\n{agent_instructions}\n"
