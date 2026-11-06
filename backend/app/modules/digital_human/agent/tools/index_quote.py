"""通过 AKShare 查询沪深重要指数的最新可用行情。"""

import asyncio
import json
import logging
import threading

import akshare as ak
import httpx
import requests
from langchain_core.tools import tool

from app.modules.digital_human.agent.tools.stock_quote import _number

INDEX_QUERY_TIMEOUT_SECONDS = 25.0
MAX_INDEX_QUERY_LENGTH = 100
MAX_INDEX_CANDIDATES = 20
INDEX_GROUP = "沪深重要指数"
INDEX_ALIASES = {
    "上证综指": "上证指数",
    "上证综合指数": "上证指数",
    "沪指": "上证指数",
    "深证指数": "深证成指",
    "深证成份指数": "深证成指",
    "深成指": "深证成指",
    "创业板指数": "创业板指",
}
logger = logging.getLogger(__name__)
# 超时不能中断 AKShare 的同步请求，槽位由实际结束的线程释放。
_index_query_slots = threading.BoundedSemaphore(2)


def _fetch_index_quote(index: str) -> dict[str, object]:
    """匹配沪深重要指数并读取行情；输入名称或代码，输出结构化观察；调用方：指数工具。"""
    if not _index_query_slots.acquire(blocking=False):
        return {"status": "unavailable", "message": "指数行情查询繁忙，请稍后重试。"}
    try:
        indices = ak.stock_zh_index_spot_em(symbol=INDEX_GROUP)
        query = INDEX_ALIASES.get(index, index)
        codes = indices["代码"].astype(str)
        names = indices["名称"].astype(str)
        if query.isascii() and query.isdigit():
            matches = indices[codes == query]
        else:
            exact = indices[names == query]
            matches = exact if not exact.empty else indices[names.str.contains(query, regex=False)]
        if matches.empty:
            return {
                "status": "not_found",
                "message": "未找到该指数，请核对名称或代码；当前支持沪深重要指数。",
            }
        if len(matches) > 1:
            if len(matches) > MAX_INDEX_CANDIDATES:
                return {
                    "status": "ambiguous",
                    "message": "匹配结果过多，请提供更完整的指数名称或代码。",
                }
            candidates = matches[["代码", "名称"]].rename(columns={"代码": "code", "名称": "name"})
            return {
                "status": "ambiguous",
                "message": "请确认指数名称或代码。",
                "candidates": candidates.to_dict(orient="records"),
            }
        match = matches.iloc[0]
        code = str(match["代码"])
        name = str(match["名称"])
        value = _number(match["最新价"])
        if value is None or value <= 0:
            return {
                "status": "no_price",
                "code": code,
                "name": name,
                "message": "暂无可用指数点位。",
            }
        return {
            "status": "ok",
            "code": code,
            "name": name,
            "value": value,
            "unit": "点",
            "change_percent": _number(match["涨跌幅"]),
            "change": _number(match["涨跌额"]),
            "quote_time": "未知",
            "delay": "未知",
            "source": "东方财富（通过 AKShare）",
        }
    finally:
        _index_query_slots.release()


@tool
async def get_index_quote(index: str) -> str:
    """查询沪深重要指数最新可用行情；输入指数名称、常用别名或六位指数代码。"""
    index = index.strip()
    if not index or len(index) > MAX_INDEX_QUERY_LENGTH:
        return json.dumps(
            {"status": "invalid", "message": "请输入有效的指数名称或代码。"}, ensure_ascii=False
        )
    try:
        # 异步等待有限时间；线程仍运行时继续占用槽位，防止反复超时耗尽资源。
        result = await asyncio.wait_for(
            asyncio.to_thread(_fetch_index_quote, index), timeout=INDEX_QUERY_TIMEOUT_SECONDS
        )
    except TimeoutError:
        result = {"status": "unavailable", "message": "指数行情查询超时，请稍后重试。"}
    except (httpx.HTTPError, requests.RequestException, KeyError, TypeError, ValueError) as error:
        logger.warning("digital_human_index_quote_failed error_type=%s", type(error).__name__)
        result = {"status": "unavailable", "message": "指数行情服务暂不可用，请稍后重试。"}
    return json.dumps(result, ensure_ascii=False, allow_nan=False)
