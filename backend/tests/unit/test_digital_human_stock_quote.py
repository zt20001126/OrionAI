import json
import time

import pandas as pd
import pytest
import requests

from app.modules.digital_human.agent.tools import stock_quote


@pytest.fixture
def stock_data(monkeypatch: pytest.MonkeyPatch) -> None:
    stocks = pd.DataFrame([
        {"code": "600519", "name": "贵州茅台"},
        {"code": "600000", "name": "浦发银行"},
        {"code": "000001", "name": "平安银行"},
    ])
    monkeypatch.setattr(stock_quote.ak, "stock_info_a_code_name", lambda: stocks)
    monkeypatch.setattr(
        stock_quote.ak,
        "stock_bid_ask_em",
        lambda symbol: pd.DataFrame({"item": ["最新", "涨幅"], "value": [100.0, -1.5]}),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("query", ["贵州茅台", "600519"])
async def test_stock_quote_returns_price_with_unknown_time(stock_data: None, query: str) -> None:
    result = json.loads(await stock_quote.get_stock_quote.ainvoke({"stock": query}))
    assert result["code"] == "600519"
    assert result["price"] == 100.0
    assert result["change_percent"] == -1.5
    assert result["quote_time"] == "未知"
    assert result["delay"] == "未知"


@pytest.mark.anyio
async def test_stock_quote_handles_ambiguous_and_unknown_stock(stock_data: None) -> None:
    ambiguous = json.loads(await stock_quote.get_stock_quote.ainvoke({"stock": "银行"}))
    assert {item["code"] for item in ambiguous["candidates"]} == {"600000", "000001"}
    missing = json.loads(await stock_quote.get_stock_quote.ainvoke({"stock": "不存在"}))
    assert missing["status"] == "not_found"


@pytest.mark.anyio
async def test_stock_quote_does_not_invent_missing_price(
    stock_data: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        stock_quote.ak, "stock_bid_ask_em",
        lambda symbol: pd.DataFrame({"item": ["最新", "涨幅"], "value": [float("nan"), 0]}),
    )
    result = json.loads(await stock_quote.get_stock_quote.ainvoke({"stock": "600519"}))
    assert result["status"] == "no_price"
    assert "price" not in result


@pytest.mark.anyio
async def test_stock_quote_timeout_returns_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_query(stock: str) -> dict[str, object]:
        time.sleep(0.1)
        return {"status": "ok"}

    monkeypatch.setattr(stock_quote, "_fetch_stock_quote", slow_query)
    monkeypatch.setattr(stock_quote, "STOCK_QUERY_TIMEOUT_SECONDS", 0.01)
    result = json.loads(await stock_quote.get_stock_quote.ainvoke({"stock": "600519"}))
    assert result["status"] == "unavailable"


@pytest.mark.anyio
async def test_stock_quote_reports_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(stock: str) -> dict[str, object]:
        raise requests.ConnectionError("upstream unavailable")

    monkeypatch.setattr(stock_quote, "_fetch_stock_quote", fail)
    result = json.loads(await stock_quote.get_stock_quote.ainvoke({"stock": "600519"}))
    assert result["status"] == "unavailable"
