"""提供基础对话 Agent 的结构化单选题卡工具。"""

from langchain_core.tools import tool

from app.agent.schemas import Question, QuestionPayload, TextQuestion


@tool("ask_user_questions", args_schema=QuestionPayload)
def ask_user_questions(questions: list[Question | TextQuestion]) -> str:
    """生成 1–3 道题卡，单选题使用 SingleChoice，自由输入题使用 Text。"""

    payload = QuestionPayload(questions=questions)
    return payload.model_dump_json()
