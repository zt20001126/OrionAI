"""从包内 Markdown 文件加载文旅智能体提示词。"""

from importlib.resources import files


def load_prompt(name: str) -> str:
    """读取随包分发的提示词文本。"""
    return (
        files("app.modules.agents.tourism_insight.prompts")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
