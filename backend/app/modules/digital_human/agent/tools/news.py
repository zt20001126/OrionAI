"""查询 GNews 新闻，返回可核验的标题、来源和发布时间。"""

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, ValidationError, field_validator

from app.core.config import get_settings

GNEWS_BASE_URL = "https://gnews.io/api/v4"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_ARTICLES = 10
BEIJING_TIMEZONE = timezone(timedelta(hours=8))
NewsCategory = Literal[
    "general",
    "world",
    "nation",
    "business",
    "technology",
    "entertainment",
    "sports",
    "science",
    "health",
]


class NewsSource(BaseModel):
    """新闻发布来源，供工具检查第三方响应。"""

    name: str


class NewsArticle(BaseModel):
    """GNews 新闻必要字段，发布时间必须包含时区。"""

    title: str
    description: str | None
    url: str
    publishedAt: datetime
    source: NewsSource

    @field_validator("publishedAt")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """校验发布时间含时区；输入第三方时间，输出时间；调用方：新闻工具。"""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("新闻发布时间缺少时区。")
        return value


class NewsResponse(BaseModel):
    """GNews 响应中供数字人使用的新闻列表。"""

    articles: list[NewsArticle]
    information: dict[str, object] | None = None


@tool
async def get_news(
    keyword: str = "",
    category: NewsCategory = "general",
    today_only: bool = False,
) -> str:
    """查询中文新闻；keyword 为关键词，category 为分类，today_only 指北京时间今天。"""
    keyword = keyword.strip()
    if len(keyword) > 200:
        return "新闻关键词不能超过 200 个字符。"
    api_key = get_settings().gnews_api_key.get_secret_value().strip()
    if not api_key:
        return "新闻服务尚未配置，请联系管理员配置 GNEWS_API_KEY。"

    # 关键词使用搜索接口；分类头条使用排行接口，均请求可为空的非必要字段。
    endpoint = "search" if keyword else "top-headlines"
    params: dict[str, str | int] = {
        "lang": "zh",
        "max": MAX_ARTICLES,
        "nullable": "description,content,image",
    }
    if keyword:
        params["q"] = keyword
    else:
        params["category"] = category
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{GNEWS_BASE_URL}/{endpoint}", params=params, headers={"X-Api-Key": api_key}
            )
            response.raise_for_status()
            result = NewsResponse.model_validate(response.json())
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 429:
            return "新闻服务调用额度或频率已达上限，请稍后再试。"
        return "新闻服务请求失败，请检查服务配置或稍后重试。"
    except (httpx.RequestError, ValueError, ValidationError):
        return "新闻服务暂时不可用或返回数据无效，请稍后再试。"

    now = datetime.now(UTC).astimezone(BEIJING_TIMEZONE)
    articles = [
        {
            "标题": article.title,
            "摘要": article.description,
            "来源": article.source.name,
            "发布时间（北京时间）": article.publishedAt.astimezone(BEIJING_TIMEZONE).isoformat(),
            "原文链接": article.url,
        }
        for article in result.articles
        if not today_only or article.publishedAt.astimezone(BEIJING_TIMEZONE).date() == now.date()
    ]
    return json.dumps(
        {
            "查询时间（北京时间）": now.isoformat(),
            "查询范围": "北京时间今天" if today_only else "接口返回的新闻",
            "说明": "仅筛选接口返回的前 10 条；数据可能延迟，不能视为实时或完整新闻。",
            "服务提示": result.information,
            "新闻": articles,
        },
        ensure_ascii=False,
    )
