"""提供基于用户本轮浏览器位置的附近服务搜索工具。"""

import json
import math
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER,
    DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
)
from app.modules.digital_human.providers.amap import AmapPoiSearchClient, AmapProviderError


class NearbyPlacesInput(BaseModel):
    """定义周边搜索的用户条件；关键词与半径由题卡收集。"""

    keyword: str = Field(min_length=1, max_length=80, description="要查找的商家或服务关键词。")
    radius_meters: int = Field(ge=1, le=50_000, description="周边搜索半径，单位米。")


@tool("search_nearby_places", args_schema=NearbyPlacesInput)
async def search_nearby_places(keyword: str, radius_meters: int, config: RunnableConfig) -> str:
    """搜索授权浏览器坐标附近的 POI；供数字人回答附近商家与服务查询。"""
    configurable: dict[str, Any] = dict((config or {}).get("configurable") or {})
    resume_answers = configurable.get("resume_answers")
    if (
        not isinstance(resume_answers, dict)
        or resume_answers.get(DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID)
        != DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER
    ):
        return json.dumps(
            {"success": False, "message": "用户尚未授权使用浏览器位置。"}, ensure_ascii=False
        )

    location = configurable.get("user_location")
    if not isinstance(location, dict) or location.get("status") != "granted":
        return json.dumps(
            {"success": False, "message": "本轮未取得浏览器位置，请重新授权定位。"},
            ensure_ascii=False,
        )
    longitude = location["longitude"]
    latitude = location["latitude"]
    accuracy = location["accuracy_meters"]
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        for value in (longitude, latitude, accuracy)
    ):
        return json.dumps(
            {"success": False, "message": "本轮浏览器位置数据无效，无法搜索附近服务。"},
            ensure_ascii=False,
        )

    try:
        pois = await AmapPoiSearchClient().search_around(
            longitude=longitude,
            latitude=latitude,
            keyword=keyword,
            radius_meters=radius_meters,
        )
    except AmapProviderError as error:
        return json.dumps({"success": False, "message": str(error)}, ensure_ascii=False)

    return json.dumps(
        {
            "success": True,
            "keyword": keyword,
            "radius_meters": radius_meters,
            "accuracy_meters": accuracy,
            "title": f"附近的{keyword}",
            "total": len(pois),
            "pois": [
                {
                    "id": poi.id,
                    "name": poi.name,
                    "address": poi.address,
                    "location": poi.location,
                    "distance": int(poi.distance_meters),
                    "tel": poi.tel,
                    "business_hours": poi.business_hours,
                    "rating": poi.rating,
                }
                for poi in pois
            ],
        },
        ensure_ascii=False,
    )
