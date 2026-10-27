"""定义技能模块可安全返回给 API 调用方的业务异常。"""


class SkillsError(Exception):
    """技能业务错误，包含稳定 HTTP 状态和中文说明。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class SkillNotFoundError(SkillsError):
    """技能不存在、已下架，或当前用户没有该关联。"""

    def __init__(self) -> None:
        super().__init__(404, "技能不存在或当前不可用。")


class SkillAlreadyAddedError(SkillsError):
    """当前用户已经添加该技能。"""

    def __init__(self) -> None:
        super().__init__(409, "该技能已添加。")


class SkillsUnavailableError(SkillsError):
    """数据库等技能服务依赖暂不可用。"""

    def __init__(self) -> None:
        super().__init__(503, "技能服务暂不可用，请稍后重试。")
