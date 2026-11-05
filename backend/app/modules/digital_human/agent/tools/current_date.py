"""提供数字人使用的北京时间日期查询工具。"""

from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


@tool
def get_current_date() -> str:
    """获取北京时间的当前日期和星期；无需输入，供数字人回答依赖当前日期的问题。"""
    current_date = datetime.now(BEIJING_TIMEZONE).date()
    return f"北京时间：{current_date.isoformat()}，{WEEKDAYS[current_date.weekday()]}"
