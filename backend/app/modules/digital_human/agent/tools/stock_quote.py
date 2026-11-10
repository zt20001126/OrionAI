"""查询沪深京 A 股最新可用行情，供数字人内部验证使用。"""

import asyncio
import json
import logging
import math
import threading

import akshare as ak
import httpx
import pandas as pd
import requests
from langchain_core.tools import tool

STOCK_QUERY_TIMEOUT_SECONDS = 25.0
MAX_STOCK_QUERY_LENGTH = 100
MAX_CANDIDATES = 20
logger = logging.getLogger(__name__)
# AKShare 使用同步网络请求；超时后线程可能仍在运行，限制同时执行的请求数。
_stock_query_slots = threading.BoundedSemaphore(2)


def _number(value: object) -> float | None:
    """将上游数字转为有限浮点数；输入行情字段，输出数字或缺失；调用方：行情查询。"""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _find_stock_matches(stock: str) -> pd.DataFrame:
    """按股票名称或代码查找候选；调用方：数字人 A 股报价和K线工具。"""
    stocks = ak.stock_info_a_code_name()
    codes = stocks["code"].astype(str)
    names = stocks["name"].astype(str)
    if stock.isascii() and stock.isdigit():
        return stocks[codes == stock]
    exact = stocks[names == stock]
    return exact if not exact.empty else stocks[names.str.contains(stock, regex=False)]


def _fetch_stock_quote(stock: str) -> dict[str, object]:
    """按名称或代码匹配 A 股并读取报价；输入查询文本，输出工具观察；调用方：行情工具。"""
    if not _stock_query_slots.acquire(blocking=False):
        return {"status": "unavailable", "message": "行情查询繁忙，请稍后重试。"}
    try:
        matches = _find_stock_matches(stock)
        if matches.empty:
            return {"status": "not_found", "message": "未找到对应的 A 股，请核对名称或代码。"}
        if len(matches) > 1:
            if len(matches) > MAX_CANDIDATES:
                return {"status": "ambiguous", "message": "匹配结果过多，请提供更完整名称或代码。"}
            return {
                "status": "ambiguous",
                "message": "请确认股票代码。",
                "candidates": matches[["code", "name"]].to_dict(orient="records"),
            }

        match = matches.iloc[0]
        code = str(match["code"])
        name = str(match["name"])
        quote = ak.stock_bid_ask_em(symbol=code).set_index("item")["value"]
        price = _number(quote["最新"])
        if price is None or price <= 0:
            return {"status": "no_price", "code": code, "name": name, "message": "暂无可用价格。"}
        change = _number(quote["涨幅"])
        return {
            "status": "ok",
            "code": code,
            "name": name,
            "price": price,
            "change_percent": change,
            "currency": "CNY",
            "quote_time": "未知",
            "delay": "未知",
            "source": "东方财富（通过 AKShare）",
        }
    finally:
        _stock_query_slots.release()


@tool
async def get_stock_quote(stock: str) -> str:
    """查询单只 A 股最新可用行情；输入股票名称或六位代码，供数字人行情问答使用。"""
    stock = stock.strip()
    if not stock or len(stock) > MAX_STOCK_QUERY_LENGTH:
        return json.dumps(
            {"status": "invalid", "message": "请输入有效的股票名称或代码。"}, ensure_ascii=False
        )
    try:
        # 超时仅结束等待；信号量由后台线程退出时释放，避免无限累积请求。
        result = await asyncio.wait_for(
            asyncio.to_thread(_fetch_stock_quote, stock), timeout=STOCK_QUERY_TIMEOUT_SECONDS
        )
    except TimeoutError:
        result = {"status": "unavailable", "message": "行情查询超时，请稍后重试。"}
    except (httpx.HTTPError, requests.RequestException, KeyError, TypeError, ValueError) as error:
        logger.warning("digital_human_stock_quote_failed error_type=%s", type(error).__name__)
        result = {"status": "unavailable", "message": "行情服务暂不可用，请稍后重试。"}
    return json.dumps(result, ensure_ascii=False, allow_nan=False)
