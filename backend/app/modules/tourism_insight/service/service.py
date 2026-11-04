"""编排文旅文件导入、评论查询、分析和结果持久化。"""

import logging
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.tourism_insight.constants import MAX_ANALYSIS_BATCH_SIZE
from app.modules.tourism_insight.errors import (
    TourismInsightConflictError,
    TourismInsightNotFoundError,
    TourismInsightValidationError,
)
from app.modules.tourism_insight.repository import repository
from app.modules.tourism_insight.schemas.schemas import (
    AnalysisItemResponse,
    AnalysisResponse,
    CommentPageResponse,
    CommentResponse,
    ImportResponse,
    MatchResponse,
    MatchRuleResponse,
    ResultGroupResponse,
    ResultsResponse,
    SummaryResponse,
)
from app.modules.tourism_insight.service.parsers import parse_scoring_rules, parse_ugc_csv

logger = logging.getLogger(__name__)


class TourismInsightService:
    """负责文旅洞察数据事务及 Agent 执行协调。"""

    def __init__(self, session: Session, agent: object | None = None) -> None:
        self._session = session
        self._agent = agent

    def import_rules(self, user_id: int, content: bytes, *, replace: bool) -> ImportResponse:
        """先解析验证新规则，再事务性清除旧匹配并替换规则。"""
        parsed, skipped, errors = parse_scoring_rules(content)
        existing = repository.count_rules(self._session, user_id)
        if existing and not replace:
            raise TourismInsightConflictError("当前已有评分规则，请确认替换后重新提交。")
        try:
            repository.replace_rules(self._session, user_id, parsed)
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return ImportResponse(
            imported_count=len(parsed),
            skipped_count=skipped,
            failed_count=len(errors),
            errors=errors,
        )

    def import_comments(self, user_id: int, content: bytes, limit: int) -> ImportResponse:
        """解析 CSV 并保存当前用户尚未导入的评论。"""
        parsed, skipped, errors = parse_ugc_csv(content, limit)
        try:
            imported = repository.import_comments(self._session, user_id, parsed)
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return ImportResponse(
            imported_count=imported,
            skipped_count=skipped + len(parsed) - imported,
            failed_count=len(errors),
            errors=errors,
        )

    def summary(self, user_id: int) -> SummaryResponse:
        rules_count = repository.count_rules(self._session, user_id)
        return SummaryResponse(
            rules_count=rules_count,
            comments_count=repository.count_comments(self._session, user_id),
            analyzed_count=repository.count_analyzed_comments(self._session, user_id),
            rules_ready=rules_count > 0,
        )

    def list_comments(self, user_id: int, *, limit: int, offset: int) -> CommentPageResponse:
        comments = repository.list_comments(self._session, user_id, limit=limit, offset=offset)
        analyzed_ids = repository.analyzed_comment_ids(
            self._session, user_id, [comment.id for comment in comments]
        )
        items = [
            self._comment_response(comment, comment.id in analyzed_ids) for comment in comments
        ]
        return CommentPageResponse(
            items=items,
            limit=limit,
            offset=offset,
            total_count=repository.count_comments(self._session, user_id),
        )

    async def analyze_comments(self, user_id: int, comment_ids: Sequence[str]) -> AnalysisResponse:
        """校验所选评论与规则后，逐条调用同一文旅 Agent 图。"""
        if repository.count_rules(self._session, user_id) == 0:
            raise TourismInsightConflictError("请先导入评分规则，再开始分析。")
        if len(comment_ids) > MAX_ANALYSIS_BATCH_SIZE:
            raise TourismInsightValidationError("单批分析评论数量超过上限。")
        ids = list(dict.fromkeys(int(comment_id) for comment_id in comment_ids))
        comments = repository.get_comments_by_ids(self._session, user_id, ids)
        comment_map = {comment.id: comment for comment in comments}
        if len(comment_map) != len(set(ids)):
            raise TourismInsightNotFoundError("部分评论不存在或无权访问。")
        items = []
        for comment_id in ids:
            try:
                await self._agent.analyze_comment(
                    user_id, comment_id, comment_map[comment_id].content
                )
                if comment_id not in repository.analyzed_comment_ids(
                    self._session, user_id, [comment_id]
                ):
                    items.append(
                        AnalysisItemResponse(
                            comment_id=str(comment_id),
                            status="failed",
                            message="该内容未进入文旅分析，请检查评论内容。",
                        )
                    )
                    continue
                items.append(
                    AnalysisItemResponse(
                        comment_id=str(comment_id), status="completed", message="分析完成"
                    )
                )
            except Exception as error:
                logger.warning(
                    "tourism_comment_analysis_failed comment_id=%s error_type=%s",
                    comment_id,
                    type(error).__name__,
                )
                items.append(
                    AnalysisItemResponse(
                        comment_id=str(comment_id), status="failed", message="分析失败，请稍后重试"
                    )
                )
        return AnalysisResponse(items=items)

    def list_results(self, user_id: int, *, limit: int, offset: int) -> ResultsResponse:
        groups = []
        for comment, rows in repository.list_results(
            self._session, user_id, limit=limit, offset=offset
        ):
            if not rows:
                continue
            matches = []
            for match, rule in rows:
                rule_response = None
                if rule is not None:
                    rule_response = MatchRuleResponse(
                        id=str(rule.id),
                        major_item=rule.major_item,
                        minor_item=rule.minor_item,
                        indicator_code=rule.indicator_code,
                        indicator_name=rule.indicator_name,
                        subitem_number=rule.subitem_number,
                        subitem_name=rule.subitem_name,
                        scoring_criterion=rule.scoring_criterion,
                        description=rule.description,
                        data_source_detail=rule.data_source_detail,
                    )
                matches.append(
                    MatchResponse(
                        status=match.status,
                        evidence=match.evidence,
                        reason=match.reason,
                        rule=rule_response,
                        sentiment=match.sentiment,
                    )
                )
            groups.append(
                ResultGroupResponse(comment=self._comment_response(comment, True), matches=matches)
            )
        return ResultsResponse(items=groups, limit=limit, offset=offset)

    def search_rules(self, user_id: int, query: str) -> list[dict[str, object]]:
        return [
            {
                "id": str(rule.id),
                "indicator_name": rule.indicator_name,
                "subitem_name": rule.subitem_name,
                "scoring_criterion": rule.scoring_criterion,
                "description": rule.description,
                "data_source_detail": rule.data_source_detail,
            }
            for rule in repository.search_rules(self._session, user_id, query)
        ]

    def save_analysis(
        self,
        user_id: int,
        text: str,
        source_comment_id: str | None,
        matches: list[dict[str, object]],
    ) -> int:
        """为手动输入建立评论，或替换已有评论结果并提交。"""
        try:
            if source_comment_id is None:
                comment = repository.create_manual_comment(self._session, user_id, text)
                comment_id = comment.id
            else:
                comment_id = int(source_comment_id)
                if not repository.get_comment(self._session, user_id, comment_id):
                    raise TourismInsightNotFoundError("评论不存在或无权访问。")
            rule_ids = [
                int(match["rule_id"]) for match in matches if match.get("rule_id") is not None
            ]
            if repository.get_rules_by_ids(self._session, user_id, rule_ids) != set(rule_ids):
                raise TourismInsightConflictError("评分规则已变更，请重新分析评论。")
            persisted_matches = [
                {
                    **match,
                    "rule_id": int(match["rule_id"]) if match.get("rule_id") is not None else None,
                }
                for match in matches
            ]
            repository.replace_comment_matches(
                self._session,
                user_id=user_id,
                comment_id=comment_id,
                matches=persisted_matches,
            )
            self._session.commit()
            return comment_id
        except SQLAlchemyError:
            self._session.rollback()
            raise

    @staticmethod
    def _comment_response(comment: object, analyzed: bool) -> CommentResponse:
        return CommentResponse(
            id=str(comment.id),
            source_type=comment.source_type,
            nickname=comment.nickname,
            ugc_type=comment.ugc_type,
            platform=comment.platform,
            title=comment.title,
            content=comment.content,
            published_at=comment.published_at,
            analyzed=analyzed,
        )
