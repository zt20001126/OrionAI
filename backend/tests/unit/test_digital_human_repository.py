from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.conversations.models.models import Conversation
from app.modules.digital_human.repository.repository import (
    count_conversations,
    list_conversations,
)
from app.modules.skills.models import Skill


def test_history_query_only_returns_current_users_digital_human_conversations() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            owner = User(account="owner@example.com", password_hash="hash")
            other = User(account="other@example.com", password_hash="hash")
            digital_human = Skill(code="digital_human", name="数字人助手", type="agent")
            general_chat = Skill(code="general_chat", name="对话助手", type="agent")
            session.add_all([owner, other, digital_human, general_chat])
            session.flush()
            expected = Conversation(user_id=owner.id, skill_code="digital_human", title="数字人")
            session.add_all(
                [
                    expected,
                    Conversation(user_id=owner.id, skill_code="general_chat"),
                    Conversation(user_id=other.id, skill_code="digital_human"),
                ]
            )
            session.commit()

            assert count_conversations(session, owner.id) == 1
            page = list_conversations(session, owner.id, limit=10, offset=0)

            assert [conversation.id for conversation in page] == [expected.id]
            assert page[0].skill_code == "digital_human"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
