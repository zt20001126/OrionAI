"""加载数字人专属系统提示词。"""

from pathlib import Path

_PROMPT_PATH = Path(__file__).with_name("system.md")


def load_digital_human_prompt() -> str:
    """读取数字人专属身份和对话风格。"""

    return _PROMPT_PATH.read_text(encoding="utf-8").strip()
