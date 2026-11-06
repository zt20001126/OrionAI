"""提供数字人根据文字描述生成并保存图片的工具。"""

import json
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.modules.digital_human.providers.image_generation import DigitalHumanImageProviderError
from app.modules.digital_human.service.image_generation import generate_and_save_image

logger = logging.getLogger(__name__)


class GenerateDigitalHumanImageInput(BaseModel):
    """只允许模型提供图片描述，用户和会话标识由服务端上下文注入。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=8_000, description="用户要求生成的画面描述")


@tool("generate_image", args_schema=GenerateDigitalHumanImageInput)
async def generate_image(prompt: str, config: RunnableConfig) -> str:
    """按用户描述生成图片并保存到当前会话；调用方：数字人 LangGraph。"""
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        return _result(success=False, message="图片描述不能为空。")

    context = config["configurable"]
    try:
        task_result_id = await generate_and_save_image(
            settings=get_settings(),
            user_id=int(context["user_id"]),
            conversation_id=int(context["conversation_id"]),
            prompt=normalized_prompt,
        )
    except DigitalHumanImageProviderError as error:
        logger.warning("digital_human_image_tool_failed code=%s", error.code)
        return _result(success=False, message=error.public_message)
    except Exception as error:
        logger.warning("digital_human_image_tool_failed error_type=%s", type(error).__name__)
        return _result(success=False, message="图片生成或保存失败，请稍后重试。")
    return _result(
        success=True,
        message="图片已生成并保存。",
        task_result_id=task_result_id,
    )


def _result(*, success: bool, message: str, task_result_id: str | None = None) -> str:
    """构造图片结果文本；成功结果含任务 ID，供 Runtime 生成图片消息。"""
    result: dict[str, str | bool] = {"success": success, "message": message}
    if task_result_id is not None:
        result["task_result_id"] = task_result_id
    return json.dumps(result, ensure_ascii=False)
