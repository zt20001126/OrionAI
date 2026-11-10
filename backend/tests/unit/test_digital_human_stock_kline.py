import json
from datetime import date, timedelta

import pandas as pd
import pytest

from app.modules.digital_human.agent.tools import stock_kline


@pytest.fixture
def stock_and_history(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    stocks = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])
    rows = [
        {
            "日期": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "开盘": 10.0,
            "收盘": 11.0,
            "最高": 12.0,
            "最低": 9.0,
            "成交量": 1000.0,
        }
        for index in range(65)
    ]
    monkeypatch.setattr(stock_kline.ak, "stock_info_a_code_name", lambda: stocks)
    monkeypatch.setattr(stock_kline.ak, "stock_zh_a_hist", lambda **_kwargs: pd.DataFrame(rows))
    return rows


@pytest.mark.anyio
async def test_default_query_returns_last_60_daily_candles_and_qfq(
    stock_and_history: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    request: dict[str, str] = {}
    monkeypatch.setattr(
        stock_kline.ak,
        "stock_zh_a_hist",
        lambda **kwargs: request.update(kwargs) or pd.DataFrame(stock_and_history),
    )

    result = json.loads(await stock_kline.get_stock_kline.ainvoke({"stock": "600519"}))

    assert result["status"] == "ok"
    assert len(result["chart"]["candles"]) == 60
    assert result["chart"]["candles"][0]["date"] == "2026-01-06"
    assert request["period"] == "daily"
    assert request["adjust"] == "qfq"


@pytest.mark.anyio
@pytest.mark.parametrize("period", ["daily", "weekly", "monthly"])
async def test_period_and_date_range_are_passed_to_akshare(
    stock_and_history: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    period: str,
) -> None:
    request: dict[str, str] = {}
    monkeypatch.setattr(
        stock_kline.ak,
        "stock_zh_a_hist",
        lambda **kwargs: request.update(kwargs) or pd.DataFrame(stock_and_history[:2]),
    )

    result = json.loads(
        await stock_kline.get_stock_kline.ainvoke(
            {
                "stock": "贵州茅台",
                "period": period,
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
            }
        )
    )

    assert result["status"] == "ok"
    assert request["period"] == period
    assert request["start_date"] == "20260101"
    assert request["end_date"] == "20260102"
    assert request["adjust"] == "qfq"


@pytest.mark.anyio
async def test_invalid_dates_and_ambiguous_stock_are_reported(
    stock_and_history: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = json.loads(
        await stock_kline.get_stock_kline.ainvoke({"stock": "600519", "start_date": "2026-02-30"})
    )
    assert invalid["status"] == "invalid"

    stocks = pd.DataFrame(
        [{"code": "600000", "name": "测试银行"}, {"code": "000001", "name": "示例银行"}]
    )
    monkeypatch.setattr(stock_kline.ak, "stock_info_a_code_name", lambda: stocks)
    ambiguous = json.loads(await stock_kline.get_stock_kline.ainvoke({"stock": "银行"}))
    assert ambiguous["status"] == "ambiguous"
