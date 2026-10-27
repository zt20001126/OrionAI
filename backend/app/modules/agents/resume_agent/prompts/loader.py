"""加载简历助手提示词模板。"""

from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def load_resume_agent_prompt() -> str:
    return (
        files("app.modules.agents.resume_agent.prompts")
        .joinpath("system.md")
        .read_text(encoding="utf-8")
    )
