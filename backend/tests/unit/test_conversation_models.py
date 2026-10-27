import pytest
from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable, Table

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.conversations.models import Conversation, Message
from app.modules.skills.models import Skill


def _postgres_table_ddl(table: Table) -> str:
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_user_snowflake_primary_key_preserves_unique_account() -> None:
    table = User.__table__

    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.identity is None
    assert table.c.id.default is not None
    assert callable(table.c.id.default.arg)
    assert table.c.id.primary_key
    assert table.c.account.unique


def test_conversation_schema_matches_postgresql_requirements() -> None:
    table = Conversation.__table__
    ddl = _postgres_table_ddl(table)

    assert set(table.columns.keys()) == {
        "id",
        "user_id",
        "skill_code",
        "title",
        "created_at",
        "updated_at",
    }
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.identity is None
    assert table.c.id.default is not None
    assert callable(table.c.id.default.arg)
    assert table.c.title.nullable
    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None
    assert ddl.count("TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL") == 2

    user_foreign_key = next(iter(table.c.user_id.foreign_keys))
    assert user_foreign_key.target_fullname == "users.id"
    assert user_foreign_key.ondelete == "CASCADE"
    skill_foreign_key = next(iter(table.c.skill_code.foreign_keys))
    assert skill_foreign_key.target_fullname == "skills.code"

    index = next(
        index for index in table.indexes if index.name == "ix_conversations_user_id_updated_at"
    )
    index_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "(user_id, updated_at DESC)" in index_ddl


def test_message_schema_matches_postgresql_requirements() -> None:
    table = Message.__table__
    ddl = _postgres_table_ddl(table)

    assert set(table.columns.keys()) == {
        "id",
        "conversation_id",
        "role",
        "content",
        "created_at",
    }
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.identity is None
    assert table.c.id.default is not None
    assert callable(table.c.id.default.arg)
    assert isinstance(table.c.content.type, JSONB)
    assert table.c.created_at.server_default is not None
    assert "content JSONB NOT NULL" in ddl
    assert "CHECK (role IN ('user', 'assistant'))" in ddl

    conversation_foreign_key = next(iter(table.c.conversation_id.foreign_keys))
    assert conversation_foreign_key.target_fullname == "conversations.id"
    assert conversation_foreign_key.ondelete == "CASCADE"

    index = next(index for index in table.indexes if index.name == "ix_messages_conversation_id_id")
    index_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "(conversation_id, id)" in index_ddl


def test_sqlite_enforces_message_role_and_cascade_delete() -> None:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: object, _record: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(account="owner@example.com", password_hash="hash")
            session.add(user)
            session.flush()
            session.add(
                Skill(
                    code="general_chat",
                    name="通用对话助手",
                    type="agent",
                    status="published",
                )
            )
            session.flush()
            conversation = Conversation(user_id=user.id)
            session.add(conversation)
            session.flush()
            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content={"parts": [{"type": "text", "text": "hello"}]},
                )
            )
            session.commit()

            session.add(
                Message(
                    conversation_id=conversation.id,
                    role="system",
                    content={"parts": []},
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            user = session.scalar(select(User).where(User.account == "owner@example.com"))
            assert user is not None
            session.delete(user)
            session.commit()

            assert session.scalar(select(func.count()).select_from(Conversation)) == 0
            assert session.scalar(select(func.count()).select_from(Message)) == 0
    finally:
        engine.dispose()
