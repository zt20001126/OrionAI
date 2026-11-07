"""验证 OpenAlex 文献工具的参数、转换、重试和数字人调用。"""

import json
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from app.modules.digital_human.agent.tools import literature


def configure_client(monkeypatch, handler):
    """注入测试密钥和 HTTP MockTransport；供文献工具测试使用。"""
    monkeypatch.setattr(
        literature,
        "get_settings",
        lambda: SimpleNamespace(openalex_api_key=SecretStr("test-key")),
    )
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        literature,
        "httpx",
        SimpleNamespace(
            AsyncClient=lambda **kwargs: original_client(
                transport=httpx.MockTransport(handler), **kwargs
            ),
            RequestError=httpx.RequestError,
            HTTPStatusError=httpx.HTTPStatusError,
            Response=httpx.Response,
        ),
    )


def work_payload(**changes):
    """构造 OpenAlex 单条文献响应；供字段映射测试复用。"""
    return {
        "id": "https://openalex.org/W1",
        "display_name": "目标检测研究",
        "authorships": [{"author": {"display_name": "张三"}}],
        "publication_year": 2024,
        "publication_date": "2024-05-01",
        "primary_location": {"source": {"display_name": "测试期刊"}},
        "doi": "https://doi.org/10.1234/test",
        "cited_by_count": 7,
        "abstract_inverted_index": {"模型": [1], "提出": [0]},
        "type": "article",
        **changes,
    }


@pytest.mark.anyio
async def test_search_maps_fields_and_inclusive_year_filter(monkeypatch):
    """查询结果字段和年份过滤按约定映射。"""

    def handler(request):
        assert request.url.params["search"] == "目标检测"
        assert (
            request.url.params["filter"]
            == "from_publication_date:2020-01-01,to_publication_date:2024-12-31"
        )
        assert request.url.params["per_page"] == "3"
        assert request.url.params["api_key"] == "test-key"
        return httpx.Response(200, json={"meta": {"count": 9}, "results": [work_payload()]})

    configure_client(monkeypatch, handler)
    response = json.loads(
        await literature.search_literature.ainvoke(
            {"keyword": " 目标检测 ", "start_year": 2020, "end_year": 2024, "count": 3}
        )
    )
    assert response["total_count"] == 9
    assert response["works"][0]["abstract"] == "提出 模型"
    assert response["works"][0]["authors"] == ["张三"]


@pytest.mark.anyio
async def test_default_year_and_count_and_missing_fields(monkeypatch):
    """省略年份时按北京时间当前年过滤，数量默认五且可选字段保留空值。"""

    def handler(request):
        current_year = literature.datetime.now(literature.BEIJING_TIMEZONE).year
        assert request.url.params["filter"] == f"publication_year:{current_year}"
        assert request.url.params["per_page"] == "5"
        return httpx.Response(
            200,
            json={
                "meta": {"count": 1},
                "results": [
                    work_payload(
                        authorships=[],
                        primary_location=None,
                        doi=None,
                        cited_by_count=None,
                        abstract_inverted_index=None,
                    )
                ],
            },
        )

    configure_client(monkeypatch, handler)
    result = json.loads(await literature.search_literature.ainvoke({"keyword": "检测"}))
    work = result["works"][0]
    assert work["authors"] == [] and work["source"] is None and work["abstract"] is None
    assert work["doi"] is None and work["cited_by_count"] is None


@pytest.mark.anyio
async def test_invalid_input_and_missing_api_key(monkeypatch):
    """无效参数与缺失密钥在请求上游前明确返回。"""
    assert (
        json.loads(await literature.search_literature.ainvoke({"keyword": " "}))["status"]
        == "invalid_input"
    )
    assert (
        json.loads(
            await literature.search_literature.ainvoke(
                {"keyword": "x", "start_year": 2025, "end_year": 2020}
            )
        )["status"]
        == "invalid_input"
    )
    monkeypatch.setattr(
        literature, "get_settings", lambda: SimpleNamespace(openalex_api_key=SecretStr(""))
    )
    assert (
        json.loads(await literature.search_literature.ainvoke({"keyword": "x"}))["status"]
        == "unavailable"
    )


@pytest.mark.anyio
async def test_retries_rate_limit_and_reports_exhaustion(monkeypatch):
    """429 按有界重试次数请求，耗尽后返回失败而非空结果。"""
    attempts = 0

    def handler(_request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "0"})

    configure_client(monkeypatch, handler)
    monkeypatch.setattr(literature.asyncio, "sleep", lambda _delay: _no_sleep())
    result = json.loads(await literature.search_literature.ainvoke({"keyword": "x"}))
    assert attempts == literature.MAX_RETRIES + 1
    assert result["status"] == "error"


async def _no_sleep():
    """提供立即完成的异步等待；供重试测试使用。"""


@pytest.mark.anyio
async def test_digital_human_invokes_literature_tool(monkeypatch):
    """数字人图调用文献工具并把结果交回模型组织回答。"""
    from app.modules.digital_human.agent.runtime import DigitalHumanRuntime
    from tests.unit.test_digital_human_agent import ScriptedChatModel

    configure_client(
        monkeypatch,
        lambda _request: httpx.Response(
            200, json={"meta": {"count": 1}, "results": [work_payload()]}
        ),
    )
    model = ScriptedChatModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_literature",
                        "args": {"keyword": "目标检测", "start_year": 2024},
                        "id": "literature-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="找到一篇目标检测研究。"),
        ]
    )
    response = await DigitalHumanRuntime(chat_model=model).ainvoke("查找2024年目标检测论文")
    assert response.status == "completed"
    assert "目标检测" in response.answer
