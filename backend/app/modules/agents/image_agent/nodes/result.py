"""将图片工具输出映射到普通助手文本和受控结果 ID。"""

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.errors import AgentExecutionError
from app.modules.agents.image_agent.state import ImageAgentState


async def image_result_node(state: ImageAgentState) -> dict[str, Any]:
    message = next(
        (
            item
            for item in reversed(state.get("messages", []))
            if isinstance(item, ToolMessage) and item.name == "generate_image"
        ),
        None,
    )
    if message is None or not isinstance(message.content, str):
        raise AgentExecutionError("图片生成未返回有效结果。", code="missing_image_result")
    try:
        payload = json.loads(message.content)
    except ValueError:
        raise AgentExecutionError("图片生成结果无法读取。", code="invalid_image_result") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("success"), bool):
        raise AgentExecutionError("图片生成结果格式无效。", code="invalid_image_result")
    if payload["success"]:
        task_result_id = payload.get("task_result_id")
        if task_result_id != state.get("task_result_id") or not str(task_result_id).isdigit():
            raise AgentExecutionError("图片生成结果标识无效。", code="invalid_image_result_id")
        answer = _combine_answer(
            state.get("answer"),
            "图片已生成并保存到本次会话。",
        )
        return {
            "messages": [AIMessage(content=answer)],
            "answer": answer,
            "image_result_id": str(task_result_id),
        }
    summary = payload.get("summary")
    safe_summary = (
        summary
        if isinstance(summary, str) and summary.strip()
        else "图片生成暂时失败，请稍后重试。"
    )
    answer = _combine_answer(state.get("answer"), safe_summary[:2_000])
    return {"messages": [AIMessage(content=answer)], "answer": answer, "image_result_id": None}


def _combine_answer(prefix: str | None, result: str) -> str:
    """将生成前已流式展示的模型回复与生图结果合并为同一条消息。"""

    return "\n\n".join(part for part in (prefix.strip() if prefix else "", result) if part)
