"""为数字人提供步行、骑行和驾车路线规划工具。"""

import json
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.modules.digital_human.agent.tools.location import get_authorized_browser_location
from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.coordinates import AmapCoordinateClient
from app.modules.digital_human.providers.amap.geocoding import (
    AmapGeocodedLocation,
    AmapGeocodingClient,
)
from app.modules.digital_human.providers.amap.route_planning import AmapRoutePlanningClient

CURRENT_LOCATION_ALIASES = frozenset({"当前位置", "我的位置", "我现在的位置"})


class RoutePlanningInput(BaseModel):
    """路线规划的模型输入；端点为用户提供的地址或明确指定的当前位置，可附城市限定范围。"""

    mode: Literal["walking", "cycling", "driving"] = Field(
        description="路线方式；仅可用 walking（步行）、cycling（骑行）或 driving（驾车）。"
    )
    origin: str = Field(
        min_length=1,
        max_length=300,
        description="起点地址或地标；用户明确要求使用当前定位时填写“当前位置”。",
    )
    destination: str = Field(
        min_length=1,
        max_length=300,
        description="用户提供的终点地址或地标，不得猜测或补造。",
    )
    city: str | None = Field(
        default=None,
        max_length=50,
        description="用户提到的城市，用于限定起点和终点的地址解析范围；未提及时省略。",
    )


@tool("plan_route", args_schema=RoutePlanningInput)
async def plan_route(
    mode: Literal["walking", "cycling", "driving"],
    origin: str,
    destination: str,
    config: RunnableConfig,
    city: str | None = None,
) -> str:
    """按用户确认的方式规划路线。

    输入：mode、起终点、可选 city 和运行配置；输出：统一路线 JSON；调用方：数字人 Agent。
    """
    try:
        normalized_city = city.strip() if city and city.strip() else None
        resolved_origin = await _resolve_origin(origin, config, normalized_city)
        resolved_destination = await AmapGeocodingClient().geocode(
            destination, city=normalized_city
        )
        route = await AmapRoutePlanningClient().plan(
            mode=mode,
            origin=resolved_origin.location,
            destination=resolved_destination.location,
            origin_name=resolved_origin.name,
            destination_name=resolved_destination.name,
        )
    except AmapProviderError as error:
        return json.dumps({"success": False, "message": str(error)}, ensure_ascii=False)
    return json.dumps({"success": True, "route": route}, ensure_ascii=False)


async def _resolve_origin(
    origin: str, config: RunnableConfig, city: str | None
) -> AmapGeocodedLocation:
    """解析起点；输入地址、城市和本轮运行配置，输出高德地点；调用方：plan_route。

    起点为当前位置时仅使用本轮已授权的浏览器坐标。
    """
    normalized_origin = origin.strip()
    if normalized_origin not in CURRENT_LOCATION_ALIASES:
        return await AmapGeocodingClient().geocode(normalized_origin, city=city)

    longitude, latitude = get_authorized_browser_location(config)
    coordinate = await AmapCoordinateClient().convert_gps(f"{longitude},{latitude}")
    return AmapGeocodedLocation(name="我的位置", location=coordinate)
