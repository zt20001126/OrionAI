from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import BigInteger, CheckConstraint, create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.skills.models import Skill, UserSkill
from app.modules.skills.repository import ensure_general_chat_skill


def test_skills_models_match_postgresql_schema() -> None:
    skills_ddl = str(CreateTable(Skill.__table__).compile(dialect=postgresql.dialect()))
    user_skills_ddl = str(CreateTable(UserSkill.__table__).compile(dialect=postgresql.dialect()))

    assert "BIGINT NOT NULL" in skills_ddl
    assert "code VARCHAR(100) NOT NULL" in skills_ddl
    assert "description TEXT" in skills_ddl
    assert "CHECK (type IN ('agent', 'tool'))" in skills_ddl
    assert "CHECK (status IN ('published', 'disabled'))" in skills_ddl
    assert "BIGINT NOT NULL" in user_skills_ddl
    assert "skill_id BIGINT NOT NULL" in user_skills_ddl
    assert "user_id BIGINT NOT NULL" in user_skills_ddl
    assert "UNIQUE (user_id, skill_id)" in user_skills_ddl

    user_foreign_key = next(iter(UserSkill.__table__.c.user_id.foreign_keys))
    assert user_foreign_key.target_fullname == "users.id"
    assert any(
        isinstance(constraint, CheckConstraint) and constraint.name == "ck_skills_type"
        for constraint in Skill.__table__.constraints
    )
    assert any(
        isinstance(constraint, CheckConstraint) and constraint.name == "ck_skills_status"
        for constraint in Skill.__table__.constraints
    )
    assert all(
        isinstance(column.type, BigInteger)
        for table in Base.metadata.tables.values()
        for column in table.primary_key.columns
    )


def test_database_constraints_reject_invalid_values_and_duplicate_relations() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(account="constraints@example.com", password_hash="hash")
            skill = Skill(code="constraint_skill", name="Valid", type="agent")
            session.add_all([user, skill])
            session.commit()

            session.add(Skill(code="invalid_type", name="Invalid", type="workflow"))
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            session.add(
                Skill(
                    code="invalid_status",
                    name="Invalid status",
                    type="agent",
                    status="archived",
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            session.add(Skill(code="constraint_skill", name="Duplicate", type="agent"))
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            user = session.scalar(select(User).where(User.account == user.account))
            skill = session.scalar(select(Skill).where(Skill.code == "constraint_skill"))
            assert user is not None
            assert skill is not None
            session.add(UserSkill(user_id=user.id, skill_id=skill.id))
            session.commit()

            session.add(UserSkill(user_id=user.id, skill_id=skill.id))
            with pytest.raises(IntegrityError):
                session.flush()
    finally:
        engine.dispose()


def test_competing_adds_are_guarded_by_the_database_unique_constraint(tmp_path: Path) -> None:
    """两个请求同时通过预检查后并发写入，数据库只接受一个关联。"""

    database_url = URL.create(
        "sqlite",
        database=str(tmp_path / "skills-concurrency.db"),
    )
    engine = create_engine(database_url, connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as setup_session:
            user = User(account="race@example.com", password_hash="hash")
            skill = Skill(code="race_skill", name="Race", type="agent")
            setup_session.add_all([user, skill])
            setup_session.commit()
            user_id = user.id
            skill_id = skill.id

        barrier = Barrier(2)

        def attempt_add(_index: int) -> bool:
            with Session(engine) as check_session:
                assert (
                    check_session.scalar(
                        select(UserSkill.id).where(
                            UserSkill.user_id == user_id,
                            UserSkill.skill_id == skill_id,
                        )
                    )
                    is None
                )

            barrier.wait(timeout=5)
            with Session(engine) as session:
                session.add(UserSkill(user_id=user_id, skill_id=skill_id))
                try:
                    session.commit()
                    return True
                except IntegrityError:
                    session.rollback()
                    return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(attempt_add, range(2)))
        assert sorted(outcomes) == [False, True]

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(UserSkill)) == 1
    finally:
        engine.dispose()


def test_general_chat_seed_is_idempotent_and_preserves_admin_changes() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            ensure_general_chat_skill(session)
            skill = session.scalar(select(Skill).where(Skill.code == "general_chat"))
            assert skill is not None
            skill_id = skill.id
            skill.status = "disabled"
            skill.name = "管理员修改过的名称"
            session.commit()

            ensure_general_chat_skill(session)
            ensure_general_chat_skill(session)

            skill = session.scalar(select(Skill).where(Skill.code == "general_chat"))
            assert skill is not None
            assert skill.id == skill_id
            assert skill.status == "disabled"
            assert skill.name == "管理员修改过的名称"
            assert (
                session.scalar(
                    select(func.count()).select_from(Skill).where(Skill.code == "general_chat")
                )
                == 1
            )
    finally:
        engine.dispose()
