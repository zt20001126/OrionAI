"""加载并组合数字人助手身份与行为提示词。"""

from pathlib import Path

from app.modules.digital_human.agent.capabilities import build_capabilities_prompt

_PROMPT_DIRECTORY = Path(__file__).parent


def load_digital_human_prompt(registered_tool_names: frozenset[str]) -> str:
    """组合身份、行为及可用能力；输入注册工具名，输出提示词；调用方：数字人图。"""

    system_prompt = (_PROMPT_DIRECTORY / "system.md").read_text(encoding="utf-8").strip()
    agent_instructions = (_PROMPT_DIRECTORY / "agent.md").read_text(encoding="utf-8").strip()
    capabilities_prompt = build_capabilities_prompt(registered_tool_names)
    return f"{system_prompt}\n\n{agent_instructions}\n\n{capabilities_prompt}\n"
