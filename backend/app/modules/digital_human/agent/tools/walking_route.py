"""为数字人提供明确高德坐标之间的步行规划工具。"""

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.route import AmapRouteClient


class WalkingRouteInput(BaseModel):
    """路线工具的输入；坐标必须是高德 GCJ-02 经纬度。"""

    origin: str = Field(description="起点高德坐标，经度,纬度。")
    destination: str = Field(description="终点高德坐标，经度,纬度。")
    destination_id: str | None = Field(default=None, description="终点商家的高德 POI ID。")


@tool("plan_walking_route", args_schema=WalkingRouteInput)
async def plan_walking_route(
    origin: str, destination: str, destination_id: str | None = None
) -> str:
    """规划已知高德坐标之间的步行路线；坐标未知时不得猜测。"""
    try:
        route = await AmapRouteClient().plan(origin, destination, destination_id)
    except AmapProviderError as error:
        return json.dumps({"success": False, "message": str(error)}, ensure_ascii=False)
    return json.dumps({"success": True, "route": route}, ensure_ascii=False)
