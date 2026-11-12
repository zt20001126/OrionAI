"""调用高德步行路线服务，返回可用于展示的真实路线。"""

from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.coordinates import (
    AmapCoordinateClient,
    normalize_coordinate,
)
from app.modules.digital_human.providers.amap.poi_client import AMAP_POI_TIMEOUT_SECONDS

WALKING_URL = "https://restapi.amap.com/v5/direction/walking"


class AmapWalkingRouteClient:
    """复用高德密钥和项目 HTTP 超时调用步行规划 V5，坐标必须为 GCJ-02。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """读取高德服务配置；调用方：商家路线 API 的 ConversationService。"""
        self._settings = settings or get_settings()

    async def convert_gps(self, coordinate: str) -> str:
        """转换浏览器 WGS-84 坐标为高德坐标；调用方：路线会话服务。"""
        return await AmapCoordinateClient(self._settings).convert_gps(coordinate)

    async def plan(
        self, origin: str, destination: str, destination_id: str | None = None
    ) -> dict[str, Any]:
        """规划 GCJ-02 坐标间的步行路线；失败时抛出安全错误；调用方：商家步行路线 Service。"""
        origin = normalize_coordinate(origin)
        destination = normalize_coordinate(destination)
        api_key = self._settings.amap_api_key.get_secret_value().strip()
        if not api_key:
            raise AmapProviderError("路线规划服务尚未配置，请联系管理员。")
        params = {
            "key": api_key,
            "origin": origin,
            "destination": destination,
            "show_fields": "cost,navi,polyline",
            "output": "json",
        }
        if destination_id:
            params["destination_id"] = destination_id
        try:
            async with httpx.AsyncClient(timeout=AMAP_POI_TIMEOUT_SECONDS) as client:
                response = await client.get(WALKING_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            raise AmapProviderError("路线规划请求超时，请稍后重试。") from None
        except httpx.HTTPError:
            raise AmapProviderError("暂时无法连接路线规划服务，请稍后重试。") from None
        except ValueError:
            raise AmapProviderError("路线规划服务返回了无法识别的数据。") from None
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "1"
            or payload.get("infocode") != "10000"
        ):
            raise AmapProviderError("高德路线规划失败，请检查服务配置后重试。")
        route = payload.get("route")
        paths = route.get("paths") if isinstance(route, dict) else None
        if not isinstance(paths, list) or not paths:
            raise AmapProviderError("未找到可用的步行路线。")
        try:
            path = paths[0]
            steps = [
                {
                    "instruction": step["instruction"],
                    "distance_m": int(step["step_distance"]),
                    "polyline": step.get("polyline") or None,
                }
                for step in path["steps"]
            ]
            return {
                "mode": "walking",
                "origin": {"name": "我的位置", "location": origin},
                "destination": {"name": "目的地", "location": destination},
                "distance_m": int(path["distance"]),
                "duration_s": int(path["cost"]["duration"]),
                "steps": steps,
            }
        except (KeyError, TypeError, ValueError, IndexError):
            raise AmapProviderError("高德返回的路线数据不完整，请稍后重试。") from None
