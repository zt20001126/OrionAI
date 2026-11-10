import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    rows = [
        {**row, "日期": (today - timedelta(days=64 - index)).isoformat()}
        for index, row in enumerate(stock_and_history)
    ]
    monkeypatch.setattr(
        stock_kline.ak,
        "stock_zh_a_hist",
        lambda **kwargs: request.update(kwargs) or pd.DataFrame(rows),
    )

    result = json.loads(await stock_kline.get_stock_kline.ainvoke({"stock": "600519"}))

    assert result["status"] == "ok"
    assert len(result["chart"]["candles"]) == 60
    assert result["chart"]["candles"][0]["date"] == rows[-60]["日期"]
    assert "moving_averages" not in result["chart"]
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


@pytest.mark.anyio
async def test_requested_moving_averages_use_qfq_closes_and_warmup_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "日期": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "开盘": float(index + 10),
            "收盘": float(index + 11),
            "最高": float(index + 12),
            "最低": float(index + 9),
            "成交量": 1000.0,
        }
        for index in range(130)
    ]
    request: dict[str, str] = {}
    monkeypatch.setattr(
        stock_kline.ak,
        "stock_info_a_code_name",
        lambda: pd.DataFrame([{"code": "600519", "name": "贵州茅台"}]),
    )
    monkeypatch.setattr(
        stock_kline.ak,
        "stock_zh_a_hist",
        lambda **kwargs: request.update(kwargs) or pd.DataFrame(rows),
    )

    result = json.loads(
        await stock_kline.get_stock_kline.ainvoke(
            {
                "stock": "600519",
                "start_date": "2026-04-30",
                "end_date": "2026-05-02",
                "ma_periods": [5, 10, 20, 60],
            }
        )
    )

    assert result["status"] == "ok"
    assert [candle["date"] for candle in result["chart"]["candles"]] == [
        "2026-04-30",
        "2026-05-01",
        "2026-05-02",
    ]
    assert request["start_date"] < "20260430"
    assert result["chart"]["moving_averages"] == [
        {"period": 5, "values": [128.0, 129.0, 130.0]},
        {"period": 10, "values": [125.5, 126.5, 127.5]},
        {"period": 20, "values": [120.5, 121.5, 122.5]},
        {"period": 60, "values": [100.5, 101.5, 102.5]},
    ]


@pytest.mark.anyio
async def test_requested_ma_period_with_insufficient_history_has_no_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "日期": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "开盘": 10.0,
            "收盘": 11.0,
            "最高": 12.0,
            "最低": 9.0,
            "成交量": 1000.0,
        }
        for index in range(3)
    ]
    monkeypatch.setattr(
        stock_kline.ak,
        "stock_info_a_code_name",
        lambda: pd.DataFrame([{"code": "600519", "name": "贵州茅台"}]),
    )
    monkeypatch.setattr(stock_kline.ak, "stock_zh_a_hist", lambda **_kwargs: pd.DataFrame(rows))

    result = json.loads(
        await stock_kline.get_stock_kline.ainvoke(
            {
                "stock": "600519",
                "start_date": "2026-01-01",
                "end_date": "2026-01-03",
                "ma_periods": [60],
            }
        )
    )

    assert result["status"] == "ok"
    assert result["chart"]["moving_averages"] == [{"period": 60, "values": [None, None, None]}]
