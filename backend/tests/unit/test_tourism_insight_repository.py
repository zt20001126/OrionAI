"""验证文旅洞察业务数据的用户隔离和规则替换持久化。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.tourism_insight.models import CommentMatch, ScoringRule, UgcComment
from app.modules.tourism_insight.repository import repository


def _rule(name: str) -> dict[str, str | None]:
    return {
        "major_item": "环境",
        "minor_item": "卫生",
        "indicator_code": "A1",
        "indicator_name": "公共卫生",
        "subitem_number": "1",
        "subitem_name": name,
        "scoring_criterion": "厕所应保持干净",
        "description": None,
        "data_source_detail": None,
    }


def test_replacing_rules_clears_matches_but_keeps_comments() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(account="tourism@example.com", password_hash="hash")
            session.add(user)
            session.flush()
            rule = ScoringRule(user_id=user.id, **_rule("厕所清洁"))
            comment = UgcComment(user_id=user.id, source_type="manual", content="厕所很干净")
            session.add_all([rule, comment])
            session.flush()
            repository.replace_comment_matches(
                session,
                user_id=user.id,
                comment_id=comment.id,
                matches=[
                    {
                        "rule_id": rule.id,
                        "evidence": "厕所很干净",
                        "reason": "直接描述卫生情况",
                        "status": "matched",
                    }
                ],
            )
            session.commit()

            repository.replace_rules(session, user.id, [_rule("洗手设施")])
            session.commit()

            assert repository.count_rules(session, user.id) == 1
            assert repository.count_comments(session, user.id) == 1
            assert repository.count_analyzed_comments(session, user.id) == 0
            assert session.query(CommentMatch).count() == 0
    finally:
        engine.dispose()
