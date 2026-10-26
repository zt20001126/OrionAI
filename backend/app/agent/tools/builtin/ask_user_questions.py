"""提供基础对话 Agent 的结构化单选题卡工具。"""

from langchain_core.tools import tool

from app.agent.schemas import Question, QuestionPayload


@tool("ask_user_questions", args_schema=QuestionPayload)
def ask_user_questions(questions: list[Question]) -> str:
    """仅在用户明确要求题卡或缺少关键选择时生成 1–3 道单选题。"""

    payload = QuestionPayload(questions=questions)
    return payload.model_dump_json()
