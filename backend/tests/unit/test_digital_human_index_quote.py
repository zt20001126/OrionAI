import json
import time

import pandas as pd
import pytest
import requests

from app.modules.digital_human.agent.tools import index_quote


@pytest.fixture
def index_data(monkeypatch: pytest.MonkeyPatch) -> None:
    indices = pd.DataFrame(
        [
            {"代码": "000001", "名称": "上证指数", "最新价": 3000.5, "涨跌幅": 1.2, "涨跌额": 35.6},
            {
                "代码": "399001",
                "名称": "深证成指",
                "最新价": 9000.0,
                "涨跌幅": -0.8,
                "涨跌额": -72.0,
            },
            {"代码": "399006", "名称": "创业板指", "最新价": 1800.0, "涨跌幅": 0.2, "涨跌额": 3.6},
            {"代码": "000300", "名称": "沪深300", "最新价": 3500.0, "涨跌幅": 0.1, "涨跌额": 3.5},
        ]
    )
    monkeypatch.setattr(index_quote.ak, "stock_zh_index_spot_em", lambda symbol: indices)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("query", "code"),
    [
        ("上证指数", "000001"),
        ("沪指", "000001"),
        ("000001", "000001"),
        ("深证成指", "399001"),
        ("深成指", "399001"),
        ("创业板指数", "399006"),
        ("399006", "399006"),
        ("沪深300", "000300"),
    ],
)
async def test_index_lookup(index_data: None, query: str, code: str) -> None:
    result = json.loads(await index_quote.get_index_quote.ainvoke({"index": query}))
    assert result["status"] == "ok"
    assert result["code"] == code
    assert result["value"] > 0
    assert result["unit"] == "点"
    assert result["quote_time"] == result["delay"] == "未知"
    assert "currency" not in result


@pytest.mark.anyio
async def test_index_ambiguous_unknown_and_invalid(index_data: None) -> None:
    ambiguous = json.loads(await index_quote.get_index_quote.ainvoke({"index": "指"}))
    assert {item["code"] for item in ambiguous["candidates"]} == {"000001", "399001", "399006"}
    missing = json.loads(await index_quote.get_index_quote.ainvoke({"index": "不存在"}))
    assert missing["status"] == "not_found"
    invalid = json.loads(await index_quote.get_index_quote.ainvoke({"index": "  "}))
    assert invalid["status"] == "invalid"


@pytest.mark.anyio
async def test_index_missing_values(index_data: None, monkeypatch: pytest.MonkeyPatch) -> None:
    indices = pd.DataFrame(
        [{"代码": "000001", "名称": "上证指数", "最新价": float("nan"), "涨跌幅": 0, "涨跌额": 0}]
    )
    monkeypatch.setattr(index_quote.ak, "stock_zh_index_spot_em", lambda symbol: indices)
    result = json.loads(await index_quote.get_index_quote.ainvoke({"index": "000001"}))
    assert result["status"] == "no_price"
    assert "value" not in result


@pytest.mark.anyio
async def test_index_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(index: str) -> dict[str, object]:
        time.sleep(0.1)
        return {"status": "ok"}

    monkeypatch.setattr(index_quote, "_fetch_index_quote", slow)
    monkeypatch.setattr(index_quote, "INDEX_QUERY_TIMEOUT_SECONDS", 0.01)
    result = json.loads(await index_quote.get_index_quote.ainvoke({"index": "上证指数"}))
    assert result["status"] == "unavailable"


@pytest.mark.anyio
async def test_index_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(index: str) -> dict[str, object]:
        raise requests.ConnectionError("upstream unavailable")

    monkeypatch.setattr(index_quote, "_fetch_index_quote", fail)
    result = json.loads(await index_quote.get_index_quote.ainvoke({"index": "上证指数"}))
    assert result["status"] == "unavailable"
