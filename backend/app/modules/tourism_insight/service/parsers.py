"""将文旅评分 Excel 和 UGC CSV 解析为业务层输入。"""

import csv
import io
from datetime import datetime
from typing import Any

from openpyxl import load_workbook

from app.modules.tourism_insight.constants import (
    DEFAULT_COMMENT_IMPORT_LIMIT,
    MAX_COMMENT_LENGTH,
    MAX_IMPORT_ROWS,
    RULE_SHEET_NAME,
)
from app.modules.tourism_insight.errors import TourismInsightValidationError


def parse_scoring_rules(content: bytes) -> tuple[list[dict[str, str | None]], int, list[str]]:
    """读取指定工作表，返回合法规则、跳过数量和有限错误样例。"""
    try:
        worksheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True)[
            RULE_SHEET_NAME
        ]
    except (KeyError, OSError, ValueError):
        raise TourismInsightValidationError(
            f"Excel 文件缺少工作表「{RULE_SHEET_NAME}」或无法读取。"
        ) from None
    rows = worksheet.iter_rows(values_only=True)
    headers = [str(value or "").strip() for value in next(rows, ())]
    required = {
        "大项": "major_item",
        "分项": "minor_item",
        "指标编号": "indicator_code",
        "指标名称": "indicator_name",
        "子项序号": "subitem_number",
        "子项名称": "subitem_name",
        "评分口径(国标)": "scoring_criterion",
        "简要说明": "description",
        "数据源(细分)": "data_source_detail",
    }
    indexes = {name: headers.index(name) for name in required if name in headers}
    missing = set(required) - indexes.keys()
    if missing:
        raise TourismInsightValidationError(f"评分表缺少必要列：{'、'.join(sorted(missing))}。")
    parsed: list[dict[str, str | None]] = []
    skipped = 0
    errors: list[str] = []
    seen_rules: set[tuple[str | None, str | None, str | None]] = set()
    for row_number, row in enumerate(rows, start=2):
        record = {field: _cell(row, indexes[column]) for column, field in required.items()}
        if not all(
            record[field]
            for field in (
                "major_item",
                "minor_item",
                "indicator_code",
                "indicator_name",
                "subitem_number",
                "subitem_name",
                "scoring_criterion",
            )
        ):
            skipped += 1
            if len(errors) < 10:
                errors.append(f"第 {row_number} 行缺少必填值。")
            continue
        unique_key = (record["indicator_code"], record["subitem_number"], record["subitem_name"])
        if unique_key in seen_rules:
            skipped += 1
            continue
        seen_rules.add(unique_key)
        parsed.append(record)
    if not parsed:
        raise TourismInsightValidationError("评分表没有可导入的有效子项。")
    return parsed, skipped, errors


def parse_ugc_csv(
    content: bytes, limit: int = DEFAULT_COMMENT_IMPORT_LIMIT
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """读取 CSV 指定字段并跳过空内容和疑似商家回复。"""
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError:
        raise TourismInsightValidationError("CSV 文件需使用 UTF-8 编码。") from None
    aliases = {
        "original_id": ("序号ID", "ID", "id"),
        "nickname": ("用户昵称", "昵称"),
        "ugc_type": ("类型",),
        "platform": ("来源",),
        "title": ("标题",),
        "content": ("内容", "评论内容"),
        "published_at": ("发布时间",),
    }
    fields = reader.fieldnames or []
    columns = {
        key: next((name for name in options if name in fields), None)
        for key, options in aliases.items()
    }
    if columns["content"] is None:
        raise TourismInsightValidationError("CSV 文件缺少「内容」或「评论内容」列。")
    parsed: list[dict[str, Any]] = []
    skipped = 0
    errors: list[str] = []
    for row in reader:
        if len(parsed) >= min(limit, MAX_IMPORT_ROWS):
            break
        content_text = (row.get(columns["content"] or "") or "").strip()
        ugc_type = (row.get(columns["ugc_type"] or "") or "").strip()
        if not content_text or any(
            term in ugc_type for term in ("商家回复", "店铺回复", "商家答复")
        ):
            skipped += 1
            continue
        if len(content_text) > MAX_COMMENT_LENGTH:
            skipped += 1
            if len(errors) < 10:
                errors.append(f"第 {reader.line_num} 行评论超过文本长度上限。")
            continue
        published_at = _parse_datetime(row.get(columns["published_at"] or ""))
        parsed.append(
            {
                "source_type": "csv",
                "original_id": _optional(row, columns["original_id"]),
                "nickname": _optional(row, columns["nickname"]),
                "ugc_type": ugc_type or None,
                "platform": _optional(row, columns["platform"]),
                "title": _optional(row, columns["title"]),
                "content": content_text,
                "published_at": published_at,
            }
        )
    return parsed, skipped, errors


def _cell(row: tuple[Any, ...], index: int) -> str | None:
    return str(row[index]).strip() if index < len(row) and row[index] is not None else None


def _optional(row: dict[str, str], column: str | None) -> str | None:
    return (row.get(column or "") or "").strip() or None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
