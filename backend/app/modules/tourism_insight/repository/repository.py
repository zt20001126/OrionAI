"""封装文旅洞察业务模型的 SQLAlchemy 查询和持久化。"""

import re
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.tourism_insight.models import CommentMatch, ScoringRule, UgcComment


def count_rules(session: Session, user_id: int) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(ScoringRule).where(ScoringRule.user_id == user_id)
        )
        or 0
    )


def count_comments(session: Session, user_id: int) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(UgcComment).where(UgcComment.user_id == user_id)
        )
        or 0
    )


def count_analyzed_comments(session: Session, user_id: int) -> int:
    statement = select(func.count(func.distinct(CommentMatch.comment_id))).where(
        CommentMatch.user_id == user_id
    )
    return session.scalar(statement) or 0


def replace_rules(session: Session, user_id: int, rules: Sequence[dict[str, str | None]]) -> None:
    session.execute(delete(CommentMatch).where(CommentMatch.user_id == user_id))
    session.execute(delete(ScoringRule).where(ScoringRule.user_id == user_id))
    session.add_all(ScoringRule(user_id=user_id, **rule) for rule in rules)


def import_comments(session: Session, user_id: int, comments: Sequence[dict[str, object]]) -> int:
    imported_keys: set[tuple[str | None, str]] = set()
    new_comments = []
    for comment in comments:
        original_id = comment.get("original_id")
        platform = comment.get("platform")
        if not isinstance(original_id, str) or not original_id:
            new_comments.append(UgcComment(user_id=user_id, **comment))
            continue
        key = (platform if isinstance(platform, str) else None, original_id)
        if key in imported_keys:
            continue
        exists = session.scalar(
            select(UgcComment.id).where(
                UgcComment.user_id == user_id,
                UgcComment.platform == key[0],
                UgcComment.original_id == original_id,
            )
        )
        if exists is None:
            new_comments.append(UgcComment(user_id=user_id, **comment))
            imported_keys.add(key)
    session.add_all(new_comments)
    return len(new_comments)


def list_comments(session: Session, user_id: int, *, limit: int, offset: int) -> list[UgcComment]:
    statement = (
        select(UgcComment)
        .where(UgcComment.user_id == user_id)
        .order_by(UgcComment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def get_comments_by_ids(
    session: Session, user_id: int, comment_ids: Sequence[int]
) -> list[UgcComment]:
    statement = select(UgcComment).where(
        UgcComment.user_id == user_id, UgcComment.id.in_(comment_ids)
    )
    return list(session.scalars(statement))


def search_rules(session: Session, user_id: int, query: str) -> list[ScoringRule]:
    from app.modules.tourism_insight.constants import MAX_RULE_CANDIDATES

    rules = list(session.scalars(select(ScoringRule).where(ScoringRule.user_id == user_id)))
    tokens: list[str] = []
    for word in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", query.lower()):
        tokens.extend(word[index : index + 2] for index in range(len(word) - 1)) if len(
            word
        ) > 4 else tokens.append(word)
    tokens = list(dict.fromkeys(tokens))
    ranked = []
    for rule in rules:
        searchable = " ".join(
            (rule.indicator_name, rule.subitem_name, rule.description or "", rule.scoring_criterion)
        ).lower()
        score = sum(token in searchable for token in tokens)
        if score:
            ranked.append((score, rule))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [rule for _, rule in ranked[:MAX_RULE_CANDIDATES]]


def replace_comment_matches(
    session: Session,
    *,
    user_id: int,
    comment_id: int,
    matches: Sequence[dict[str, object]],
) -> None:
    session.execute(
        delete(CommentMatch).where(
            CommentMatch.user_id == user_id,
            CommentMatch.comment_id == comment_id,
        )
    )
    session.add_all(
        CommentMatch(user_id=user_id, comment_id=comment_id, **match) for match in matches
    )


def analyzed_comment_ids(session: Session, user_id: int, comment_ids: Sequence[int]) -> set[int]:
    if not comment_ids:
        return set()
    statement = (
        select(CommentMatch.comment_id)
        .where(
            CommentMatch.user_id == user_id,
            CommentMatch.comment_id.in_(comment_ids),
        )
        .distinct()
    )
    return set(session.scalars(statement))


def get_comment(session: Session, user_id: int, comment_id: int) -> UgcComment | None:
    return session.scalar(
        select(UgcComment).where(UgcComment.id == comment_id, UgcComment.user_id == user_id)
    )


def create_manual_comment(session: Session, user_id: int, content: str) -> UgcComment:
    comment = UgcComment(user_id=user_id, source_type="manual", content=content)
    session.add(comment)
    session.flush()
    return comment


def get_rules_by_ids(session: Session, user_id: int, rule_ids: Sequence[int]) -> set[int]:
    if not rule_ids:
        return set()
    statement = select(ScoringRule.id).where(
        ScoringRule.user_id == user_id,
        ScoringRule.id.in_(rule_ids),
    )
    return set(session.scalars(statement))


def list_results(
    session: Session, user_id: int, *, limit: int, offset: int
) -> list[tuple[UgcComment, list[tuple[CommentMatch, ScoringRule | None]]]]:
    comment_statement = (
        select(UgcComment)
        .join(CommentMatch, CommentMatch.comment_id == UgcComment.id)
        .where(UgcComment.user_id == user_id, CommentMatch.user_id == user_id)
        .group_by(UgcComment.id)
        .order_by(UgcComment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    comments = list(session.scalars(comment_statement))
    results = []
    for comment in comments:
        statement = (
            select(CommentMatch, ScoringRule)
            .outerjoin(ScoringRule, CommentMatch.rule_id == ScoringRule.id)
            .where(CommentMatch.user_id == user_id, CommentMatch.comment_id == comment.id)
            .order_by(CommentMatch.id)
        )
        results.append((comment, list(session.execute(statement))))
    return results
