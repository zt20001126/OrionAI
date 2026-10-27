"""按技能代码分派 Agent Runtime。"""

from collections.abc import Iterator, Mapping

from app.agent.runtime.protocol import AgentRuntime
from app.modules.conversations.errors import ConversationUnavailableError


class AgentRegistry(Mapping[str, AgentRuntime]):
    """持有应用生命周期内构造的不可变 Agent Runtime 集合。"""

    def __init__(self, runtimes: Mapping[str, AgentRuntime]) -> None:
        self._runtimes = dict(runtimes)

    def get(self, skill_code: str) -> AgentRuntime:
        """返回技能对应的 Runtime；未注册技能不回退到其他 Agent。"""
        try:
            return self._runtimes[skill_code]
        except KeyError:
            raise ConversationUnavailableError from None

    def __getitem__(self, skill_code: str) -> AgentRuntime:
        return self.get(skill_code)

    def __iter__(self) -> Iterator[str]:
        return iter(self._runtimes)

    def __len__(self) -> int:
        return len(self._runtimes)
