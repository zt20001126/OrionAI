"""图片助手 LangGraph 节点之间共享的类型化状态。"""

from typing import Any

from app.agent.state import ConversationState


class ImageAgentState(ConversationState, total=False):
    """保留通用消息状态，并增加图片业务推理字段。"""

    original_request: str
    is_image_generation: bool
    image_prompt: str
    generation_options: dict[str, Any]
    awaiting_image_size: bool
    task_result_id: str | None
    image_result_id: str | None
    answer: str | None
