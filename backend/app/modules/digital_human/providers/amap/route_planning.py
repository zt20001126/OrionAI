"""调用高德多方式路径规划服务并转换为会话路线结构。"""

from typing import Any, Literal

import httpx

from app.core.config import Settings, get_settings
from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.coordinates import normalize_coordinate
from app.modules.digital_human.providers.amap.poi_client import AMAP_POI_TIMEOUT_SECONDS

RouteMode = Literal["walking", "cycling", "driving"]
AMAP_ROUTE_URLS: dict[RouteMode, str] = {
    "walking": "https://restapi.amap.com/v5/direction/walking",
    "cycling": "https://restapi.amap.com/v5/direction/bicycling",
    "driving": "https://restapi.amap.com/v5/direction/driving",
}
ROUTE_MODE_NAMES: dict[RouteMode, str] = {
    "walking": "步行",
    "cycling": "骑行",
    "driving": "驾车",
}


class AmapRoutePlanningClient:
    """按步行、骑行或驾车方式调用高德 V5 路线接口。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """读取高德服务配置；调用方：数字人路线规划 Agent Tool。"""
        self._settings = settings or get_settings()

    async def plan(
        self,
        mode: RouteMode,
        origin: str,
        destination: str,
        origin_name: str,
        destination_name: str,
    ) -> dict[str, Any]:
        """规划两个 GCJ-02 坐标间的路线。

        输入：路线方式、端点坐标和地点名称；输出：统一路线结果；调用方：路线 Agent Tool。
        """
        normalized_origin = normalize_coordinate(origin)
        normalized_destination = normalize_coordinate(destination)
        api_key = self._settings.amap_api_key.get_secret_value().strip()
        if not api_key:
            raise AmapProviderError("路线规划服务尚未配置，请联系管理员。")

        try:
            async with httpx.AsyncClient(timeout=AMAP_POI_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    AMAP_ROUTE_URLS[mode],
                    params={
                        "key": api_key,
                        "origin": normalized_origin,
                        "destination": normalized_destination,
                        "show_fields": "cost,navi,polyline",
                        "output": "json",
                    },
                )
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
            raise AmapProviderError("高德路线规划失败，请检查路线信息后重试。")

        route = payload.get("route")
        paths = route.get("paths") if isinstance(route, dict) else None
        if not isinstance(paths, list) or not paths:
            raise AmapProviderError(f"未找到可用的{ROUTE_MODE_NAMES[mode]}路线。")

        try:
            path = paths[0]
            if not isinstance(path, dict):
                raise ValueError
            cost = path["cost"]
            raw_steps = path["steps"]
            if not isinstance(cost, dict):
                raise ValueError
            if not isinstance(raw_steps, list) or not raw_steps:
                raise ValueError
            steps = [_parse_route_step(step) for step in raw_steps]
            return {
                "mode": mode,
                "origin": {"name": origin_name, "location": normalized_origin},
                "destination": {"name": destination_name, "location": normalized_destination},
                "distance_m": int(path["distance"]),
                "duration_s": int(cost["duration"]),
                "steps": steps,
            }
        except (KeyError, TypeError, ValueError):
            raise AmapProviderError("高德返回的路线数据不完整，请稍后重试。") from None


def _parse_route_step(step: object) -> dict[str, Any]:
    """校验并映射高德路线步骤。

    输入：高德 API step；输出：指示、距离和轨迹字段；调用方：路线 Provider。
    """
    if not isinstance(step, dict):
        raise ValueError("路线步骤格式无效。")
    instruction = step.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("路线步骤缺少指示。")
    polyline = step.get("polyline")
    if polyline is not None and not isinstance(polyline, str):
        raise ValueError("路线步骤轨迹格式无效。")
    return {
        "instruction": instruction,
        "distance_m": int(step["step_distance"]),
        "polyline": polyline or None,
    }
