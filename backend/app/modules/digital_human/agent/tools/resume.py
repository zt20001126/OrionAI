"""提供数字人读取和保存当前用户简历的工具。"""

import json
from collections.abc import Callable
from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.resume.errors import ResumeError
from app.modules.resume.schemas import (
    ResumeContent,
    ResumeResponse,
    ResumeSaveRequest,
    ResumeStyleConfig,
)

GET_RESUME_TOOL_NAME = "get_resume"
SAVE_RESUME_TOOL_NAME = "save_resume"


class GetResumeToolInput(BaseModel):
    """查询当前用户简历的空参数工具输入。"""

    model_config = ConfigDict(extra="forbid")


class SaveResumeToolInput(BaseModel):
    """保存简历工具输入，结构与现有简历保存接口一致。"""

    model_config = ConfigDict(extra="forbid")

    content: ResumeContent = Field(description="完整简历内容，未修改的部分必须保留。")
    style_config: ResumeStyleConfig = Field(description="排版设置，未修改时沿用查询结果。")
    expected_updated_at: datetime | None = Field(
        default=None,
        description="查询简历得到的更新时间；新用户尚无已保存简历时为 null。",
    )


def create_resume_tools(
    reader: Callable[[int], ResumeResponse],
    writer: Callable[[int, ResumeSaveRequest], ResumeResponse],
) -> list[BaseTool]:
    """构造复用简历服务的查询和保存工具；调用方：数字人 LangGraph。"""

    @tool(GET_RESUME_TOOL_NAME, args_schema=GetResumeToolInput)
    def get_resume(config: RunnableConfig) -> str:
        """查询当前登录用户的完整简历、排版设置和版本。"""
        user_id = _current_user_id(config)
        if user_id is None:
            return _error_result("当前用户身份不可用，无法读取简历。")
        try:
            resume = reader(user_id)
        except ResumeError as error:
            return _error_result(error.detail)
        return json.dumps(
            {"success": True, "data": resume.model_dump(mode="json")},
            ensure_ascii=False,
        )

    @tool(SAVE_RESUME_TOOL_NAME, args_schema=SaveResumeToolInput)
    def save_resume(
        config: RunnableConfig,
        content: ResumeContent,
        style_config: ResumeStyleConfig,
        expected_updated_at: datetime | None = None,
    ) -> str:
        """保存完整简历；数字人须先展示变更并取得用户确认，再调用此工具。"""
        user_id = _current_user_id(config)
        if user_id is None:
            return _error_result("当前用户身份不可用，简历没有保存。")
        try:
            request = ResumeSaveRequest(
                content=content,
                style_config=style_config,
                expected_updated_at=expected_updated_at,
            )
            resume = writer(user_id, request)
        except ValidationError:
            return _error_result("简历内容不完整或格式无效，请检查后再试。")
        except ResumeError as error:
            return _error_result(error.detail)
        return json.dumps(
            {"success": True, "data": resume.model_dump(mode="json")},
            ensure_ascii=False,
        )

    return [get_resume, save_resume]


def _current_user_id(config: RunnableConfig) -> int | None:
    """从可信运行配置读取当前用户 ID；调用方：数字人简历工具。"""
    configurable = dict((config or {}).get("configurable") or {})
    user_id = configurable.get("user_id")
    if isinstance(user_id, int) and not isinstance(user_id, bool) and user_id > 0:
        return user_id
    return None


def _error_result(message: str) -> str:
    """生成数字人可识别的简历工具失败结果。"""
    return json.dumps({"success": False, "message": message}, ensure_ascii=False)
