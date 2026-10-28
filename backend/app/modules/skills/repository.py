"""封装技能相关 SQLAlchemy 查询，不处理 HTTP 或业务错误。"""

from datetime import datetime

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.modules.skills.models import Skill, UserSkill

GENERAL_CHAT_SKILL_CODE = "general_chat"
GENERAL_CHAT = {
    "code": GENERAL_CHAT_SKILL_CODE,
    "name": "对话助手",
    "description": "支持日常问答和多轮对话",
    "type": "agent",
    "status": "published",
}
IMAGE_AGENT = {
    "code": "image_agent",
    "name": "图片助手",
    "description": "根据文字生成电商商品主图和详情页图片",
    "type": "agent",
    "status": "published",
}
RESUME_ASSISTANT = {
    "code": "resume_assistant",
    "name": "简历助手",
    "description": "编辑和分析简历，提供优化建议、岗位方向与面试准备。",
    "type": "agent",
    "status": "published",
}


def list_market_skills(
    session: Session,
    user_id: int,
    *,
    skill_type: str | None,
    keyword: str | None,
    include_disabled: bool = False,
    page: int,
    page_size: int,
) -> tuple[list[tuple[Skill, bool]], int]:
    """分页查询技能，并通过单次外连接获取用户添加状态。"""

    filters = [] if include_disabled else [Skill.status == "published"]
    if skill_type is not None:
        filters.append(Skill.type == skill_type)
    if keyword:
        escape_character = chr(92)
        escaped_keyword = (
            keyword.replace(escape_character, escape_character * 2)
            .replace("%", f"{escape_character}%")
            .replace("_", f"{escape_character}_")
        )
        filters.append(Skill.name.ilike(f"%{escaped_keyword}%", escape=escape_character))

    total = session.scalar(select(func.count()).select_from(Skill).where(*filters)) or 0
    statement = (
        select(Skill, UserSkill.id.is_not(None))
        .outerjoin(
            UserSkill,
            and_(UserSkill.skill_id == Skill.id, UserSkill.user_id == user_id),
        )
        .where(*filters)
        .order_by(Skill.created_at.desc(), Skill.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(session.execute(statement).tuples()), total


def get_market_skill(session: Session, user_id: int, skill_id: int) -> tuple[Skill, bool] | None:
    """读取已发布技能详情及当前用户的添加状态。"""

    statement = (
        select(Skill, UserSkill.id.is_not(None))
        .outerjoin(
            UserSkill,
            and_(UserSkill.skill_id == Skill.id, UserSkill.user_id == user_id),
        )
        .where(Skill.id == skill_id, Skill.status == "published")
    )
    result = session.execute(statement).first()
    return (result[0], result[1]) if result is not None else None


def list_user_skills(session: Session, user_id: int) -> list[tuple[Skill, datetime]]:
    """按添加时间倒序列出当前用户已添加且仍发布的技能。"""

    statement = (
        select(Skill, UserSkill.created_at)
        .join(UserSkill, UserSkill.skill_id == Skill.id)
        .where(UserSkill.user_id == user_id, Skill.status == "published")
        .order_by(UserSkill.created_at.desc(), UserSkill.id.desc())
    )
    return list(session.execute(statement).tuples())


def get_published_skill(session: Session, skill_id: int) -> Skill | None:
    """查找可供新用户添加的技能。"""

    return session.scalar(select(Skill).where(Skill.id == skill_id, Skill.status == "published"))


def user_has_skill(session: Session, user_id: int, skill_id: int) -> bool:
    """检查用户是否已有技能关联。"""

    return (
        session.scalar(
            select(UserSkill.id).where(
                UserSkill.user_id == user_id,
                UserSkill.skill_id == skill_id,
            )
        )
        is not None
    )


def user_has_skill_code(session: Session, user_id: int, skill_code: str) -> bool:
    """检查用户是否已添加指定代码且仍发布的技能。"""

    statement = (
        select(UserSkill.id)
        .join(Skill, UserSkill.skill_id == Skill.id)
        .where(
            UserSkill.user_id == user_id,
            Skill.code == skill_code,
            Skill.status == "published",
        )
    )
    return session.scalar(statement) is not None


def add_user_skill(session: Session, user_id: int, skill: Skill) -> UserSkill:
    """创建用户技能关联并 flush，以便数据库约束立即校验。"""

    user_skill = UserSkill(user_id=user_id, skill_id=skill.id, skill_name=skill.name)
    session.add(user_skill)
    session.flush()
    return user_skill


def remove_user_skill(session: Session, user_id: int, skill_id: int) -> bool:
    """只删除指定用户自己的关联记录。"""

    result = session.execute(
        delete(UserSkill).where(
            UserSkill.user_id == user_id,
            UserSkill.skill_id == skill_id,
        )
    )
    return result.rowcount == 1


def ensure_general_chat_skill(session: Session) -> None:
    """幂等创建对话助手技能，不覆盖已存在技能的管理员配置。"""

    values = GENERAL_CHAT.copy()
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = (
            postgresql_insert(Skill)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Skill.code])
        )
    elif dialect_name == "sqlite":
        statement = (
            sqlite_insert(Skill)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Skill.code])
        )
    else:
        if session.scalar(select(Skill.id).where(Skill.code == GENERAL_CHAT["code"])) is None:
            session.add(Skill(**values))
        session.commit()
        return
    session.execute(statement)
    session.commit()


def ensure_image_agent_skill(session: Session) -> None:
    """幂等发布图片助手市场条目，不覆盖管理员后续修改。"""
    values = IMAGE_AGENT.copy()
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = (
            postgresql_insert(Skill)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Skill.code])
        )
    elif dialect_name == "sqlite":
        statement = (
            sqlite_insert(Skill)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Skill.code])
        )
    else:
        if session.scalar(select(Skill.id).where(Skill.code == IMAGE_AGENT["code"])) is None:
            session.add(Skill(**values))
        session.commit()
        return
    session.execute(statement)
    session.commit()


def ensure_resume_assistant_skill(session: Session) -> None:
    """幂等发布简历助手，并保留已有技能 ID 和用户关联。"""
    values = RESUME_ASSISTANT.copy()
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = (
            postgresql_insert(Skill)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Skill.code],
                set_={
                    "status": "published",
                    "name": values["name"],
                    "description": values["description"],
                },
            )
        )
    elif dialect_name == "sqlite":
        statement = (
            sqlite_insert(Skill)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Skill.code],
                set_={
                    "status": "published",
                    "name": values["name"],
                    "description": values["description"],
                },
            )
        )
    else:
        skill = session.scalar(select(Skill).where(Skill.code == RESUME_ASSISTANT["code"]))
        if skill is None:
            session.add(Skill(**values))
        else:
            skill.status = "published"
            skill.name = values["name"]
            skill.description = values["description"]
        session.commit()
        return
    session.execute(statement)
    session.commit()
