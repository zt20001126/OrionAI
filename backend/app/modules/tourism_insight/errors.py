"""定义文旅洞察接口可返回的业务错误。"""


class TourismInsightError(Exception):
    """文旅洞察业务错误基类。"""

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class TourismInsightNotFoundError(TourismInsightError):
    """请求的评论或分析结果不存在或不属于当前用户。"""

    status_code = 404


class TourismInsightConflictError(TourismInsightError):
    """当前文旅洞察业务状态不允许该操作。"""

    status_code = 409


class TourismInsightValidationError(TourismInsightError):
    """上传文件或请求内容不符合文旅洞察约定。"""

    status_code = 422
