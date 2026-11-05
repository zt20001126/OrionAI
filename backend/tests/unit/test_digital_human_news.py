"""验证 GNews 请求、北京时间筛选及失败处理。"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.modules.digital_human.agent.tools import news


def configure_client(monkeypatch, handler):
    """替换新闻客户端和密钥；输入测试响应处理器；调用方：新闻工具测试。"""
    monkeypatch.setattr(
        news, "get_settings", lambda: SimpleNamespace(gnews_api_key=SecretStr("test-key"))
    )
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        news.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.anyio
async def test_news_search_filters_today_and_uses_header(monkeypatch):
    """仅返回北京时间今天的数据，密钥只通过请求头发送。"""
    now = datetime.now(UTC)

    def handler(request):
        assert request.url.path == "/api/v4/search"
        assert request.url.params["q"] == "科技"
        assert "apikey" not in request.url.params
        assert request.headers["X-Api-Key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "title": "今天",
                        "description": "摘要",
                        "url": "https://example.com/1",
                        "publishedAt": now.isoformat(),
                        "source": {"name": "来源"},
                    },
                    {
                        "title": "旧闻",
                        "description": None,
                        "url": "https://example.com/2",
                        "publishedAt": (now - timedelta(days=2)).isoformat(),
                        "source": {"name": "来源"},
                    },
                ]
            },
        )

    configure_client(monkeypatch, handler)
    result = json.loads(await news.get_news.ainvoke({"keyword": "科技", "today_only": True}))
    assert [article["标题"] for article in result["新闻"]] == ["今天"]
    assert result["新闻"][0]["原文链接"] == "https://example.com/1"


@pytest.mark.anyio
async def test_news_provider_failure_is_reported(monkeypatch):
    """限流与无效响应不被伪装成成功结果。"""
    configure_client(monkeypatch, lambda request: httpx.Response(429))
    assert "上限" in await news.get_news.ainvoke({})


@pytest.mark.anyio
async def test_news_missing_key(monkeypatch):
    """没有配置密钥时不请求上游。"""
    monkeypatch.setattr(news, "get_settings", lambda: SimpleNamespace(gnews_api_key=SecretStr("")))
    assert "尚未配置" in await news.get_news.ainvoke({})


@pytest.mark.anyio
async def test_digital_human_invokes_news_tool(monkeypatch):
    """验证数字人图会调用新闻工具并把结果交还模型。"""
    from langchain_core.messages import AIMessage

    from app.modules.digital_human.agent.runtime import DigitalHumanRuntime
    from tests.unit.test_digital_human_agent import ScriptedChatModel

    configure_client(monkeypatch, lambda request: httpx.Response(200, json={"articles": []}))
    model = ScriptedChatModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_news",
                        "args": {"today_only": True},
                        "id": "news-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="今天暂无符合条件的新闻。"),
        ]
    )
    response = await DigitalHumanRuntime(chat_model=model).ainvoke("今天有什么新闻")
    assert response.status == "completed"
    assert "新闻" in response.answer


@pytest.mark.anyio
async def test_news_rejects_invalid_response(monkeypatch):
    """第三方响应缺少必要字段时明确报告失败。"""
    configure_client(monkeypatch, lambda request: httpx.Response(200, json={"articles": [{}]}))
    assert "无效" in await news.get_news.ainvoke({})
