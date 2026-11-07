"""淘客易商品 Provider、工具参数和数字人图集成测试。"""

import json
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr, ValidationError

from app.modules.digital_human.agent.tools import products
from app.modules.digital_human.providers.tky import TkyClient, TkyProviderError


def tky_settings(token: str = "test-token") -> SimpleNamespace:
    """构造不含真实凭据的 TKY 测试配置。"""
    return SimpleNamespace(
        tky_api_token=SecretStr(token),
        tky_api_base_url="https://api.example.test/openapi/v1",
    )


def mocked_client(monkeypatch: pytest.MonkeyPatch, handler):
    """将 Provider 的 HTTP 请求发送到 MockTransport。"""
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.modules.digital_human.providers.tky.client.get_settings",
        lambda: tky_settings(),
    )
    monkeypatch.setattr(
        "app.modules.digital_human.providers.tky.client.httpx.AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )


def product_payload(goodsid: int = 123) -> dict[str, object]:
    """返回官方商品字段结构的测试数据。"""
    return {
        "goodsid": goodsid,
        "itemid": "Taobao-AbC",
        "title": "测试蓝牙耳机",
        "description": "测试描述",
        "mainimage": "https://example.test/product.jpg",
        "images": ["https://example.test/product.jpg"],
        "itemlink": "https://item.taobao.com/item.htm?id=42",
        "categoryid": 7,
        "price": 99.0,
        "couponamount": 10.0,
        "dailysales": 20,
        "unrelated_large_field": "must not be returned",
    }


@pytest.mark.anyio
async def test_search_sends_filters_auth_and_keeps_goodsid(monkeypatch):
    """搜索映射筛选参数并保留可供详情调用的 goodsid。"""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openapi/v1/goods"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.url.params["keyword"] == "耳机"
        assert request.url.params["minprice"] == "50"
        assert request.url.params["maxprice"] == "150"
        assert request.url.params["sort"] == "daily_sales"
        assert request.url.params["page"] == "2"
        assert request.url.params["size"] == "10"
        return httpx.Response(200, json={"code": 0, "data": {"items": [product_payload()]}})

    mocked_client(monkeypatch, handler)
    result = await TkyClient().search_goods(
        {
            "keyword": "耳机", "minprice": 50, "maxprice": 150,
            "sort": "daily_sales", "page": 2, "size": 10,
        }
    )
    assert result["items"][0]["goodsid"] == 123
    assert "unrelated_large_field" not in result["items"][0]


@pytest.mark.anyio
async def test_detail_uses_tky_record_id(monkeypatch):
    """详情路径使用淘客易记录 ID，而非商品 itemid。"""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openapi/v1/goods/123"
        return httpx.Response(200, json={"code": 0, "data": product_payload()})

    mocked_client(monkeypatch, handler)
    assert (await TkyClient().get_goods_detail(123))["goodsid"] == 123


@pytest.mark.anyio
async def test_missing_token_fails_without_http_request(monkeypatch):
    """未配置 Token 时明确返回配置错误，不发起网络请求。"""
    monkeypatch.setattr(
        "app.modules.digital_human.providers.tky.client.get_settings",
        lambda: tky_settings(""),
    )
    with pytest.raises(TkyProviderError, match="TKY_API_TOKEN"):
        await TkyClient().get_goods_detail(123)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "认证失败"), (404, "没有找到"), (429, "频繁")],
)
async def test_upstream_http_errors_are_safe(status, expected, monkeypatch):
    """鉴权、商品不存在和限流错误不会暴露上游响应内容。"""
    mocked_client(monkeypatch, lambda _request: httpx.Response(status, text="secret upstream body"))
    with pytest.raises(TkyProviderError, match=expected):
        await TkyClient().get_goods_detail(123)


@pytest.mark.anyio
async def test_timeout_returns_actionable_error(monkeypatch):
    """网络超时转换为可恢复的 Provider 错误。"""
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    mocked_client(monkeypatch, handler)
    with pytest.raises(TkyProviderError, match="超时"):
        await TkyClient().get_goods_detail(123)


def test_search_parameter_validation():
    """搜索参数拒绝超长关键词、负价格、反向价格区间和越界分页。"""
    with pytest.raises(ValidationError):
        products.SearchProductsInput(keyword="x" * 61)
    with pytest.raises(ValidationError):
        products.SearchProductsInput(minprice=-1)
    with pytest.raises(ValidationError):
        products.SearchProductsInput(minprice=20, maxprice=10)
    with pytest.raises(ValidationError):
        products.SearchProductsInput(size=51)


@pytest.mark.anyio
async def test_empty_search_result_is_explicit(monkeypatch):
    """无匹配商品时工具输出明确的空结果信息。"""
    async def empty_search(_self, _params):
        return {"items": [], "page": 1, "size": 20, "hasmore": False}

    monkeypatch.setattr(products.TkyClient, "search_goods", empty_search)
    output = json.loads(await products.search_products.ainvoke({"keyword": "不存在的商品"}))
    assert output["items"] == []
    assert output["message"] == "没有找到符合条件的商品。"


@pytest.mark.anyio
async def test_graph_registers_tools_and_resolves_second_search_result(monkeypatch):
    """数字人图注册两个工具并用先前搜索结果中的 ID 查询第二款详情。"""
    from app.modules.digital_human.agent.runtime import DigitalHumanRuntime
    from tests.unit.test_digital_human_agent import ScriptedChatModel

    calls: list[tuple[str, object]] = []

    async def search_goods(_self, params):
        calls.append(("search", params))
        return {"items": [product_payload(101), product_payload(202)], "page": 1, "size": 20}

    async def get_goods_detail(_self, goodsid):
        calls.append(("detail", goodsid))
        return product_payload(goodsid)

    monkeypatch.setattr(products.TkyClient, "search_goods", search_goods)
    monkeypatch.setattr(products.TkyClient, "get_goods_detail", get_goods_detail)
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[{
                "name": "search_products", "args": {"keyword": "耳机", "maxprice": 100},
                "id": "search-1", "type": "tool_call",
            }]),
            AIMessage(content="找到两款耳机。"),
            AIMessage(content="", tool_calls=[{
                "name": "get_product_detail", "args": {"goodsid": 202},
                "id": "detail-1", "type": "tool_call",
            }]),
            AIMessage(content="第二款是测试蓝牙耳机，售价 99 元。"),
        ]
    )
    from langgraph.checkpoint.memory import MemorySaver

    runtime = DigitalHumanRuntime(chat_model=model, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "tky-products-test"}}
    first = await runtime.ainvoke("搜索 100 元以内耳机", runnable_config=config)
    second = await runtime.ainvoke("介绍一下第二款", runnable_config=config)
    assert first.answer == "找到两款耳机。"
    assert "99 元" in second.answer
    assert calls[0][0] == "search"
    assert calls[0][1]["maxprice"] == 100
    assert calls[1] == ("detail", 202)
