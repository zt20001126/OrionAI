"""查询沪深京 A 股日、周、月历史 K 线。"""

import asyncio
import json
import logging
import threading
from datetime import date, datetime, timedelta
from math import fsum
from typing import Literal
from zoneinfo import ZoneInfo

import akshare as ak
import httpx
import requests
from langchain_core.tools import tool

from app.modules.digital_human.agent.tools.stock_quote import (
    MAX_CANDIDATES,
    MAX_STOCK_QUERY_LENGTH,
    _find_stock_matches,
    _number,
)

KLINE_QUERY_TIMEOUT_SECONDS = 30.0
MAX_KLINE_CANDLES = 300
PERIOD_LOOKBACK_DAYS = {"daily": 180, "weekly": 1095, "monthly": 2190}
MA_WARMUP_DAYS = {"daily": 180, "weekly": 450, "monthly": 2190}
logger = logging.getLogger(__name__)
_kline_query_slots = threading.BoundedSemaphore(2)


def _query_kline(
    stock: str,
    period: Literal["daily", "weekly", "monthly"],
    start_date: str | None,
    end_date: str | None,
    ma_periods: list[int] | None,
) -> dict[str, object]:
    """查询并规范化股票 K 线。

    输入：股票、周期、区间及可选 MA 周期；输出：工具结果；调用方：数字人 K 线工具。
    """
    if not _kline_query_slots.acquire(blocking=False):
        return {"status": "unavailable", "message": "K线查询繁忙，请稍后重试。"}
    try:
        matches = _find_stock_matches(stock)
        if matches.empty:
            return {"status": "not_found", "message": "未找到对应 A 股，请核对名称或代码。"}
        if len(matches) > 1:
            if len(matches) > MAX_CANDIDATES:
                return {"status": "ambiguous", "message": "匹配结果过多，请提供股票代码。"}
            return {
                "status": "ambiguous",
                "message": "匹配到多只股票，请确认代码。",
                "candidates": matches[["code", "name"]].to_dict(orient="records"),
            }

        match = matches.iloc[0]
        code = str(match["code"])
        name = str(match["name"])
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        end = date.fromisoformat(end_date) if end_date else today
        start = (
            date.fromisoformat(start_date)
            if start_date
            else end - timedelta(days=PERIOD_LOOKBACK_DAYS[period])
        )
        if end > today:
            return {"status": "invalid", "message": "结束日期不能晚于今天。"}
        if start > end:
            return {"status": "invalid", "message": "开始日期不能晚于结束日期。"}
        if (end - start).days > 3650:
            return {"status": "invalid", "message": "K线查询区间不能超过 10 年。"}
        fetch_start = start - timedelta(days=MA_WARMUP_DAYS[period]) if ma_periods else start
        frame = ak.stock_zh_a_hist(
            symbol=code,
            period=period,
            start_date=fetch_start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )
        if frame.empty:
            return {"status": "no_data", "message": "该区间没有可用的历史K线。"}

        candles: list[dict[str, object]] = []
        for _, row in frame.iterrows():
            open_price = _number(row["开盘"])
            close_price = _number(row["收盘"])
            high_price = _number(row["最高"])
            low_price = _number(row["最低"])
            if open_price is None or close_price is None or high_price is None or low_price is None:
                continue
            if low_price <= 0 or low_price > min(open_price, close_price):
                continue
            if high_price < max(open_price, close_price):
                continue
            candles.append(
                {
                    "date": str(row["日期"]),
                    "open": open_price,
                    "close": close_price,
                    "high": high_price,
                    "low": low_price,
                    "volume": _number(row["成交量"]),
                }
            )
        if not candles:
            return {"status": "no_data", "message": "该区间没有有效的历史K线。"}
        candles.sort(key=lambda candle: str(candle["date"]))
        visible_candles = [
            candle
            for candle in candles
            if start.isoformat() <= str(candle["date"]) <= end.isoformat()
        ]
        if not visible_candles:
            return {"status": "no_data", "message": "该区间没有可用的历史K线。"}
        if start_date is None and end_date is None:
            visible_candles = visible_candles[-60:]
        elif len(visible_candles) > MAX_KLINE_CANDLES:
            return {
                "status": "invalid",
                "message": f"查询结果超过 {MAX_KLINE_CANDLES} 根K线，请缩短日期范围。",
            }
        chart = {
            "code": code,
            "name": name,
            "period": period,
            "adjust": "qfq",
            "start_date": str(visible_candles[0]["date"]),
            "end_date": str(visible_candles[-1]["date"]),
            "source": "东方财富（通过 AKShare）",
            "candles": visible_candles,
        }
        if ma_periods:
            chart["moving_averages"] = _calculate_moving_averages(
                candles,
                visible_candles,
                ma_periods,
            )
        return {"status": "ok", "chart": chart}
    finally:
        _kline_query_slots.release()


def _calculate_moving_averages(
    candles: list[dict[str, object]],
    visible_candles: list[dict[str, object]],
    periods: list[int],
) -> list[dict[str, object]]:
    """按完整历史收盘价计算可见区间 SMA。

    输入：完整和可见 K 线及周期；输出：按可见 K 线对齐的均线；调用方：数字人 K 线工具。
    """
    candle_indexes = {str(candle["date"]): index for index, candle in enumerate(candles)}
    close_prices = [float(candle["close"]) for candle in candles]
    series: list[dict[str, object]] = []
    for period in sorted(set(periods)):
        values: list[float | None] = []
        for candle in visible_candles:
            candle_index = candle_indexes[str(candle["date"])]
            window_start = candle_index - period + 1
            values.append(
                fsum(close_prices[window_start : candle_index + 1]) / period
                if window_start >= 0
                else None
            )
        series.append({"period": period, "values": values})
    return series


@tool
async def get_stock_kline(
    stock: str,
    period: Literal["daily", "weekly", "monthly"] = "daily",
    start_date: str | None = None,
    end_date: str | None = None,
    ma_periods: list[Literal[5, 10, 20, 60]] | None = None,
) -> str:
    """查询单只 A 股前复权日、周或月 K 线，并返回状态和图表 JSON。

    输入：股票、周期、日期及可选 MA 周期；调用方：数字人 Agent。
    仅用户明确要求 MA／均线时传入 ma_periods；未指定周期时传入 5、10、20、60。
    """
    stock = stock.strip()
    if not stock or len(stock) > MAX_STOCK_QUERY_LENGTH:
        return json.dumps(
            {"status": "invalid", "message": "请输入有效股票名称或代码。"}, ensure_ascii=False
        )
    if start_date:
        start_date = _parse_date(start_date)
        if start_date is None:
            return json.dumps(
                {"status": "invalid", "message": "开始日期格式应为 YYYY-MM-DD。"},
                ensure_ascii=False,
            )
    if end_date:
        end_date = _parse_date(end_date)
        if end_date is None:
            return json.dumps(
                {"status": "invalid", "message": "结束日期格式应为 YYYY-MM-DD。"},
                ensure_ascii=False,
            )
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_query_kline, stock, period, start_date, end_date, ma_periods),
            timeout=KLINE_QUERY_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        result = {"status": "unavailable", "message": "K线查询超时，请稍后重试。"}
    except (httpx.HTTPError, requests.RequestException, KeyError, TypeError, ValueError) as error:
        logger.warning("digital_human_stock_kline_failed error_type=%s", type(error).__name__)
        result = {"status": "unavailable", "message": "K线服务暂不可用，请稍后重试。"}
    return json.dumps(result, ensure_ascii=False, allow_nan=False)


def _parse_date(value: str) -> str | None:
    """校验用户日期并统一为 ISO 格式；供K线工具处理外部日期参数。"""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None
