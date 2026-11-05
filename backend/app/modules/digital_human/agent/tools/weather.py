"""通过 Open-Meteo 查询指定地点的当前天气。"""

import json

import httpx
from langchain_core.tools import tool

from app.modules.digital_human.agent.tools.current_date import get_current_date

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 10.0
WEATHER_DESCRIPTIONS = {
    0: "晴", 1: "大致晴朗", 2: "局部多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨", 56: "小冻毛毛雨", 57: "大冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "小冻雨", 67: "大冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒", 80: "小阵雨", 81: "中阵雨",
    82: "强阵雨", 85: "小阵雪", 86: "大阵雪", 95: "雷暴", 96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


@tool
async def get_current_weather(location: str) -> str:
    """查询指定城市当前天气；输入城市及必要的省份或国家，供数字人天气问答调用。"""
    location = location.strip()
    if not location or len(location) > 100:
        return "地点无效，请提供城市名称。"

    # 查询前获取日期；天气数据仍以服务返回的当地时间为准。
    beijing_date = get_current_date.invoke({})
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(
            GEOCODING_URL, params={"name": location, "count": 5, "language": "zh"}
        )
        response.raise_for_status()
        places = response.json().get("results", [])
        if not places:
            return "没有找到该地点，请用户提供更完整的城市名称。"
        if len(places) > 1:
            candidates = [
                ", ".join(
                    part
                    for part in (place["name"], place.get("admin1"), place.get("country"))
                    if part
                )
                for place in places
            ]
            return json.dumps({"需要确认地点": candidates}, ensure_ascii=False)

        place = places[0]
        response = await client.get(
            WEATHER_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        weather = response.json()
        current = weather["current"]
        return json.dumps(
            {
                "地点": ", ".join(
                    part
                    for part in (place["name"], place.get("admin1"), place.get("country"))
                    if part
                ),
                "当地时间": weather["current"]["time"],
                "查询时的北京时间日期": beijing_date,
                "时区": weather["timezone"],
                "当前天气": current,
                "天气现象": WEATHER_DESCRIPTIONS.get(current["weather_code"], "未知"),
                "单位": weather["current_units"],
                "数据来源": "Open-Meteo，当前天气为模型数据",
            },
            ensure_ascii=False,
        )
