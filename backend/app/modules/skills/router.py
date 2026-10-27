"""定义技能市场和当前用户技能 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.modules.auth.dependencies import validate_origin
from app.modules.skills.dependencies import CurrentUser, SkillsServiceDependency
from app.modules.skills.schemas import (
    MAX_SNOWFLAKE_ID,
    AddSkillRequest,
    MySkillsResponse,
    SkillPageResponse,
    SkillResponse,
    SkillType,
)

router = APIRouter(prefix="/v1", tags=["skills"])
SnowflakeIdPath = Annotated[int, Path(gt=0, le=MAX_SNOWFLAKE_ID)]


@router.get("/skills", response_model=SkillPageResponse)
def list_market_skills(
    user: CurrentUser,
    service: SkillsServiceDependency,
    skill_type: Annotated[SkillType | None, Query(alias="type")] = None,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
    include_disabled: Annotated[
        bool,
        Query(description="是否同时返回已停用技能；停用技能仍不可添加。"),
    ] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SkillPageResponse:
    """分页查询已发布技能市场。"""

    return service.list_market(
        user,
        skill_type=skill_type,
        keyword=keyword,
        include_disabled=include_disabled,
        page=page,
        page_size=page_size,
    )


@router.get("/skills/{skill_id}", response_model=SkillResponse)
def get_skill_detail(
    skill_id: SnowflakeIdPath,
    user: CurrentUser,
    service: SkillsServiceDependency,
) -> SkillResponse:
    """读取已发布技能详情。"""

    return service.get_detail(user, skill_id)


@router.get("/users/me/skills", response_model=MySkillsResponse)
def list_my_skills(user: CurrentUser, service: SkillsServiceDependency) -> MySkillsResponse:
    """查询当前用户已添加且仍发布的技能。"""

    return service.list_my_skills(user)


@router.post(
    "/users/me/skills",
    response_model=SkillResponse,
    status_code=201,
    dependencies=[Depends(validate_origin)],
)
def add_my_skill(
    payload: AddSkillRequest,
    user: CurrentUser,
    service: SkillsServiceDependency,
) -> SkillResponse:
    """将已发布技能添加到当前用户列表。"""

    return service.add_skill(user, int(payload.skill_id))


@router.delete(
    "/users/me/skills/{skill_id}",
    status_code=204,
    dependencies=[Depends(validate_origin)],
)
def remove_my_skill(
    skill_id: SnowflakeIdPath,
    user: CurrentUser,
    service: SkillsServiceDependency,
) -> Response:
    """移除当前用户与技能的关联。"""

    service.remove_skill(user, skill_id)
    return Response(status_code=204)
