"""简历模块向 API 暴露的稳定业务错误。"""


class ResumeError(RuntimeError):
    status_code = 503
    detail = "简历服务暂时不可用。"


class ResumeNotFoundError(ResumeError):
    status_code = 404
    detail = "尚未保存简历。"


class ResumeUnavailableError(ResumeError):
    detail = "简历服务暂时不可用。"


class ResumeConflictError(ResumeError):
    status_code = 409
    detail = "简历已在其他位置更新，请重新加载后再保存。"


class ResumePhotoError(ResumeError):
    status_code = 400
    detail = "简历照片无效或暂时不可用。"


class ResumePhotoStorageError(ResumeError):
    status_code = 503
    detail = "简历照片存储暂时不可用。"


class ResumePdfError(ResumeError):
    status_code = 503
    detail = "PDF 暂时无法生成，请稍后重试。"
