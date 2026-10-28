"""构造简历优化候选的确认题卡和可读预览。"""

from typing import Any

from app.agent.schemas import Question, QuestionOption
from app.modules.resume.schemas import ResumeContent, TiptapDocument, document_text


def build_optimization_question(candidate: dict[str, Any]) -> Question:
    """将优化候选展示为预览题卡，并提供确认、重生成或取消选项。"""
    preview = _candidate_preview(candidate)
    return Question(
        id="resume_optimization",
        title="请预览优化建议，并选择下一步。",
        context=preview,
        type="SingleChoice",
        options=[
            QuestionOption(
                label="确认采用并保存", description="检查简历版本后，将候选内容写入已保存简历。"
            ),
            QuestionOption(label="重新生成候选", description="保留原简历，继续调整优化方向。"),
            QuestionOption(label="取消本次优化", description="不保存本次候选。"),
            QuestionOption(label="暂不处理", description="关闭本次确认，不修改简历。"),
        ],
        allow_custom_input=False,
    )


def _candidate_preview(candidate: dict[str, Any]) -> str:
    patch = candidate.get("patch", {})
    changes: list[str] = []
    basic = patch.get("basic_info")
    if isinstance(basic, dict):
        changes.append(f"求职意向：{basic.get('intended_position', '')}")
    if isinstance(patch.get("skills"), dict):
        skills = ResumeContent.model_validate({"skills": patch["skills"]}).skills
        changes.append(f"专业技能：\n{document_text(skills)}")
    for key, label in (("works", "工作经历"), ("projects", "项目经历")):
        entries = patch.get(key)
        if isinstance(entries, list):
            for entry in entries:
                document = TiptapDocument.model_validate(entry["content"])
                changes.append(
                    f"{label}第 {entry['index'] + 1} 项正文：\n{document_text(document)}"
                )
    preview = "本次候选只修改以下职业内容：\n\n" + "\n\n".join(changes)
    if len(preview) > 2_800:
        return preview[:2_780].rstrip() + "\n\n……预览已截断，确认前请继续核对以上内容。"
    return preview
