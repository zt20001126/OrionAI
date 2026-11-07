"""通过 OpenAlex 检索文献并整理数字人展示所需字段。"""

import asyncio
import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 0.5
MAX_RETRY_AFTER_SECONDS = 5.0
DEFAULT_RESULT_COUNT = 5
MAX_RESULT_COUNT = 100
MAX_KEYWORD_LENGTH = 200
BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


class OpenAlexAuthor(BaseModel):
    """OpenAlex 列表结果中的作者展示字段。"""

    display_name: str | None = None


class OpenAlexAuthorship(BaseModel):
    """一条作者署名记录。"""

    author: OpenAlexAuthor | None = None


class OpenAlexSource(BaseModel):
    """文献来源的展示字段。"""

    display_name: str | None = None


class OpenAlexLocation(BaseModel):
    """文献主要位置及其来源。"""

    source: OpenAlexSource | None = None


class OpenAlexWork(BaseModel):
    """校验文献查询中使用的 OpenAlex 字段。"""

    id: str
    display_name: str
    authorships: list[OpenAlexAuthorship] = []
    publication_year: int | None = None
    publication_date: str | None = None
    primary_location: OpenAlexLocation | None = None
    doi: str | None = None
    cited_by_count: int | None = None
    abstract_inverted_index: dict[str, list[int]] | None = None
    type: str | None = None


class OpenAlexWorksResponse(BaseModel):
    """校验 OpenAlex 文献列表及匹配总数。"""

    meta: dict[str, Any]
    results: list[OpenAlexWork]


def _reconstruct_abstract(index: dict[str, list[int]] | None) -> str | None:
    """按 OpenAlex 倒排位置还原摘要；供文献响应转换调用。"""
    if not index:
        return None
    words: dict[int, str] = {}
    for word, positions in index.items():
        for position in positions:
            if not isinstance(position, int) or position < 0 or position in words:
                raise ValueError("OpenAlex 摘要词序无效。")
            words[position] = word
    if not words or set(words) != set(range(max(words) + 1)):
        raise ValueError("OpenAlex 摘要词序不连续。")
    return " ".join(words[position] for position in range(len(words)))


def _year_filter(start_year: int, end_year: int) -> str:
    """生成包含起止年份的 OpenAlex 日期过滤条件。"""
    if start_year == end_year:
        return f"publication_year:{start_year}"
    return f"from_publication_date:{start_year}-01-01,to_publication_date:{end_year}-12-31"


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """计算有上限的重试等待时间；429 优先采用 Retry-After。"""
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        try:
            return min(max(float(retry_after), 0.0), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            pass
    return RETRY_DELAY_SECONDS * (2**attempt)


async def _request_works(params: dict[str, str | int]) -> OpenAlexWorksResponse:
    """请求并校验 OpenAlex；仅对限流、服务端错误和网络错误有限重试。"""
    response: httpx.Response | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(OPENALEX_WORKS_URL, params=params)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return OpenAlexWorksResponse.model_validate(response.json())
        except httpx.RequestError:
            if attempt == MAX_RETRIES:
                raise
            response = None
        except (ValueError, ValidationError):
            raise

        if attempt == MAX_RETRIES:
            response.raise_for_status()
        await asyncio.sleep(_retry_delay(response, attempt))
    raise RuntimeError("OpenAlex 请求重试结束。")


@tool
async def search_literature(
    keyword: str,
    start_year: int | None = None,
    end_year: int | None = None,
    count: int = DEFAULT_RESULT_COUNT,
) -> str:
    """按关键词、年份和数量查询 OpenAlex 文献；供数字人文献检索调用。"""
    keyword = keyword.strip()
    if not keyword:
        return json.dumps(
            {"status": "invalid_input", "message": "请提供文献检索关键词。"}, ensure_ascii=False
        )
    if len(keyword) > MAX_KEYWORD_LENGTH:
        return json.dumps(
            {"status": "invalid_input", "message": "关键词不能超过 200 个字符。"},
            ensure_ascii=False,
        )
    if not 1 <= count <= MAX_RESULT_COUNT:
        return json.dumps(
            {"status": "invalid_input", "message": "查询数量请设置为 1 到 100 条。"},
            ensure_ascii=False,
        )

    current_year = datetime.now(BEIJING_TIMEZONE).year
    if start_year is None and end_year is None:
        start_year = end_year = current_year
    elif start_year is None:
        start_year = end_year
    elif end_year is None:
        end_year = start_year
    if start_year is None or end_year is None or start_year < 1000 or end_year < start_year:
        return json.dumps(
            {
                "status": "invalid_input",
                "message": "年份无效，请提供不早于 1000 年且顺序正确的年份。",
            },
            ensure_ascii=False,
        )

    api_key = get_settings().openalex_api_key.get_secret_value().strip()
    if not api_key:
        return json.dumps(
            {
                "status": "unavailable",
                "message": "文献服务尚未配置，请联系管理员配置 OPENALEX_API_KEY。",
            },
            ensure_ascii=False,
        )

    params: dict[str, str | int] = {
        "api_key": api_key,
        "search": keyword,
        "filter": _year_filter(start_year, end_year),
        "per_page": count,
        "select": (
            "id,display_name,authorships,publication_year,publication_date,"
            "primary_location,doi,cited_by_count,abstract_inverted_index,type"
        ),
    }
    try:
        result = await _request_works(params)
        works = [
            {
                "title": work.display_name,
                "authors": [
                    author.author.display_name
                    for author in work.authorships
                    if author.author and author.author.display_name
                ],
                "publication_year": work.publication_year,
                "publication_date": work.publication_date,
                "source": (
                    work.primary_location.source.display_name
                    if work.primary_location and work.primary_location.source
                    else None
                ),
                "doi": work.doi,
                "cited_by_count": work.cited_by_count,
                "abstract": _reconstruct_abstract(work.abstract_inverted_index),
                "type": work.type,
                "openalex_url": work.id,
            }
            for work in result.results
        ]
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        message = (
            "文献服务请求过于频繁，请稍后再试。"
            if status == 429
            else "文献服务暂时不可用，请稍后再试。"
        )
        return json.dumps({"status": "error", "message": message}, ensure_ascii=False)
    except (httpx.RequestError, ValueError, ValidationError, TypeError):
        return json.dumps(
            {"status": "error", "message": "文献服务连接失败或返回数据无效，请稍后再试。"},
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "status": "success",
            "query": {"keyword": keyword, "start_year": start_year, "end_year": end_year},
            "requested_count": count,
            "total_count": result.meta.get("count"),
            "returned_count": len(works),
            "works": works,
        },
        ensure_ascii=False,
    )
