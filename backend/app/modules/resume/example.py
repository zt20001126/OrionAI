"""为尚未保存简历的用户提供算法工程师示例。"""

from uuid import UUID

from app.modules.resume.schemas import (
    BasicInfo,
    EducationItem,
    ProjectItem,
    ResumeContent,
    SkillsDocument,
    WorkItem,
    document_from_text,
)


def example_resume() -> ResumeContent:
    """构造可编辑的示例简历；无输入，返回简历内容；由简历服务首次读取时调用。"""
    return ResumeContent(
        basic_info=BasicInfo(
            name="张三",
            phone="13800000000",
            email="zhangsan@example.com",
            intended_position="算法工程师",
            work_experience_years=3,
        ),
        educations=[
            EducationItem(
                id=UUID("d85a7344-4c7d-4437-a5da-cd4cbfcf2a01"),
                school="示例大学",
                major="计算机科学与技术",
                degree="本科",
                start_month="2017-09",
                end_month="2021-06",
            )
        ],
        skills=SkillsDocument.model_validate(
            document_from_text(
                "熟悉 Python、SQL 和常用数据处理工具。\n"
                "掌握机器学习基础，熟悉 PyTorch 和模型训练流程。"
            ).model_dump()
        ),
        works=[
            WorkItem(
                id=UUID("d85a7344-4c7d-4437-a5da-cd4cbfcf2a02"),
                company="示例科技有限公司",
                position="算法工程师",
                start_month="2021-07",
                end_month="2024-06",
                content=document_from_text("负责数据处理、模型训练与评估，协助算法服务上线。"),
            )
        ],
        projects=[
            ProjectItem(
                id=UUID("d85a7344-4c7d-4437-a5da-cd4cbfcf2a03"),
                name="用户兴趣推荐项目",
                role="算法工程师",
                technology_stack="Python、PyTorch、SQL",
                start_month="2023-01",
                end_month="2023-12",
                content=document_from_text("整理用户行为数据，参与推荐模型训练与效果评估。"),
            )
        ],
    )
