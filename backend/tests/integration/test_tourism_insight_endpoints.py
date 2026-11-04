"""验证文旅分析结果接口的情感字段和用户数据隔离。"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application import create_app
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.tourism_insight.models import CommentMatch, UgcComment


@asynccontextmanager
async def _test_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """结果接口测试不启动模型或外部 Checkpointer。"""

    yield


def test_results_return_sentiment_and_keep_user_scope() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as session:
        current_user = User(account="tourism-current@example.com", password_hash="hash")
        other_user = User(account="tourism-other@example.com", password_hash="hash")
        session.add_all([current_user, other_user])
        session.flush()
        current_comment = UgcComment(
            user_id=current_user.id,
            source_type="manual",
            content="大厅指引清晰",
        )
        historical_comment = UgcComment(
            user_id=current_user.id,
            source_type="manual",
            content="历史分析记录",
        )
        other_comment = UgcComment(
            user_id=other_user.id,
            source_type="manual",
            content="他人的评论",
        )
        session.add_all([current_comment, historical_comment, other_comment])
        session.flush()
        session.add_all(
            [
                CommentMatch(
                    user_id=current_user.id,
                    comment_id=current_comment.id,
                    evidence="大厅指引清晰",
                    status="unmatched",
                    sentiment="positive",
                ),
                CommentMatch(
                    user_id=current_user.id,
                    comment_id=historical_comment.id,
                    evidence="历史分析记录",
                    status="unmatched",
                    sentiment=None,
                ),
                CommentMatch(
                    user_id=other_user.id,
                    comment_id=other_comment.id,
                    evidence="他人的评论",
                    status="unmatched",
                    sentiment="negative",
                ),
            ]
        )
        session.commit()
        session.refresh(current_user)

    state: dict[str, Any] = {"user": current_user}
    test_app = create_app(lifespan=_test_lifespan)

    def override_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_current_user() -> User:
        return state["user"]

    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_current_user] = override_current_user
    try:
        with TestClient(test_app) as client:
            response = client.get("/api/tourism-insight/results")

        assert response.status_code == 200
        groups = response.json()["items"]
        assert {group["comment"]["content"] for group in groups} == {
            "大厅指引清晰",
            "历史分析记录",
        }
        sentiments = {
            group["comment"]["content"]: group["matches"][0]["sentiment"] for group in groups
        }
        assert sentiments == {"大厅指引清晰": "positive", "历史分析记录": None}
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
