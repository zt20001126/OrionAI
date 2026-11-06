"""提供数字人文生视频工具。"""

import json
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.modules.digital_human.service.video_generation import generate_and_save_video

logger = logging.getLogger(__name__)


class GenerateVideoInput(BaseModel):
    """模型提供视频描述，用户和会话由服务端上下文提供。"""

    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=8000, description="视频画面与动作描述")


@tool("generate_video", args_schema=GenerateVideoInput)
async def generate_video(prompt: str, config: RunnableConfig) -> str:
    """为当前会话生成并保存视频；输入画面描述，输出任务结果；调用方：数字人。"""
    prompt = prompt.strip()
    if not prompt:
        return json.dumps({"success": False, "message": "视频描述不能为空。"}, ensure_ascii=False)
    context = config["configurable"]
    try:
        task_id = await generate_and_save_video(
            settings=get_settings(),
            user_id=int(context["user_id"]),
            conversation_id=int(context["conversation_id"]),
            prompt=prompt,
        )
    except Exception as error:
        logger.warning("digital_human_video_tool_failed error_type=%s", type(error).__name__)
        return json.dumps(
            {
                "success": False,
                "message": "视频生成或保存未完成，请联系管理员确认任务状态后再重试。",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"success": True, "message": "视频已生成并保存。", "task_result_id": task_id},
        ensure_ascii=False,
    )
