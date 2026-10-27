"""实现技能查询、用户添加和移除规则，并协调数据库事务。"""

from typing import NoReturn

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.skills import repository
from app.modules.skills.errors import (
    SkillAlreadyAddedError,
    SkillNotFoundError,
    SkillsUnavailableError,
)
from app.modules.skills.models import Skill
from app.modules.skills.schemas import (
    MySkillResponse,
    MySkillsResponse,
    SkillPageResponse,
    SkillResponse,
)


class SkillsService:
    """编排技能仓储调用、业务校验和事务提交。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_market(
        self,
        user: User,
        *,
        skill_type: str | None,
        keyword: str | None,
        include_disabled: bool = False,
        page: int,
        page_size: int,
    ) -> SkillPageResponse:
        """查询技能市场。

        Step 1: 将搜索、类型和停用状态筛选条件传给 Repository。
        Step 2: 将查询结果转换为 API 响应 DTO。
        """

        try:
            rows, total = repository.list_market_skills(
                self._session,
                user.id,
                skill_type=skill_type,
                keyword=keyword.strip() if keyword else None,
                include_disabled=include_disabled,
                page=page,
                page_size=page_size,
            )
        except SQLAlchemyError:
            self._database_error()
        return SkillPageResponse(
            items=[self._skill_response(skill, is_added) for skill, is_added in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_detail(self, user: User, skill_id: int) -> SkillResponse:
        try:
            result = repository.get_market_skill(self._session, user.id, skill_id)
        except SQLAlchemyError:
            self._database_error()
        if result is None:
            raise SkillNotFoundError
        skill, is_added = result
        return self._skill_response(skill, is_added)

    def list_my_skills(self, user: User) -> MySkillsResponse:
        try:
            rows = repository.list_user_skills(self._session, user.id)
        except SQLAlchemyError:
            self._database_error()
        return MySkillsResponse(
            items=[
                MySkillResponse(
                    **self._skill_response(skill, True).model_dump(),
                    added_at=added_at,
                )
                for skill, added_at in rows
            ]
        )

    def add_skill(self, user: User, skill_id: int) -> SkillResponse:
        try:
            skill = repository.get_published_skill(self._session, skill_id)
            if skill is None:
                raise SkillNotFoundError
            if repository.user_has_skill(self._session, user.id, skill_id):
                raise SkillAlreadyAddedError

            repository.add_user_skill(self._session, user.id, skill)
            self._session.commit()
            return self._skill_response(skill, True)
        except (SkillAlreadyAddedError, SkillNotFoundError):
            self._session.rollback()
            raise
        except IntegrityError as error:
            self._session.rollback()
            if self._is_duplicate_user_skill(error):
                raise SkillAlreadyAddedError from None
            raise SkillsUnavailableError from None
        except SQLAlchemyError:
            self._database_error()

    def remove_skill(self, user: User, skill_id: int) -> None:
        try:
            removed = repository.remove_user_skill(self._session, user.id, skill_id)
            if not removed:
                raise SkillNotFoundError
            self._session.commit()
        except SkillNotFoundError:
            self._session.rollback()
            raise
        except SQLAlchemyError:
            self._database_error()

    @staticmethod
    def _skill_response(skill: Skill, is_added: bool) -> SkillResponse:
        return SkillResponse(
            id=str(skill.id),
            code=skill.code,
            name=skill.name,
            description=skill.description,
            type=skill.type,
            status=skill.status,
            created_at=skill.created_at,
            is_added=is_added,
        )

    @staticmethod
    def _is_duplicate_user_skill(error: IntegrityError) -> bool:
        """只将用户技能联合唯一约束冲突映射为重复添加。"""

        constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint_name == "uq_user_skills_user_skill":
            return True
        return "UNIQUE constraint failed: user_skills.user_id, user_skills.skill_id" in str(
            error.orig
        )

    def _database_error(self) -> NoReturn:
        self._session.rollback()
        raise SkillsUnavailableError from None
