"""封装高德坐标校验与坐标系转换。"""

import math

import httpx

from app.core.config import Settings, get_settings
from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.poi_client import AMAP_POI_TIMEOUT_SECONDS

AMAP_COORDINATE_CONVERT_URL = "https://restapi.amap.com/v3/assistant/coordinate/convert"


def normalize_coordinate(value: str) -> str:
    """校验经纬度并限制六位小数；输入经度在前，输出规范坐标；调用方：高德路线和地图 Provider。"""
    try:
        parts = value.split(",")
        if len(parts) != 2:
            raise ValueError
        longitude, latitude = (float(part) for part in parts)
        if not (math.isfinite(longitude) and math.isfinite(latitude)):
            raise ValueError
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError
    except (ValueError, TypeError):
        raise AmapProviderError("路线坐标无效，请重新获取位置。") from None
    return f"{longitude:.6f},{latitude:.6f}"


class AmapCoordinateClient:
    """使用服务端高德 Key 将浏览器 GPS 坐标转换为高德 GCJ-02。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """读取高德服务配置；调用方：路线规划及路线会话服务。"""
        self._settings = settings or get_settings()

    async def convert_gps(self, coordinate: str) -> str:
        """转换 WGS-84 坐标；输入经度在前的经纬度，输出 GCJ-02；调用方：高德路线工具。"""
        normalized_coordinate = normalize_coordinate(coordinate)
        api_key = self._settings.amap_api_key.get_secret_value().strip()
        if not api_key:
            raise AmapProviderError("路线规划服务尚未配置，请联系管理员。")

        try:
            async with httpx.AsyncClient(timeout=AMAP_POI_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    AMAP_COORDINATE_CONVERT_URL,
                    params={
                        "key": api_key,
                        "locations": normalized_coordinate,
                        "coordsys": "gps",
                        "output": "json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            raise AmapProviderError("坐标转换超时，请稍后重试。") from None
        except httpx.HTTPError:
            raise AmapProviderError("无法连接高德坐标转换服务，请稍后重试。") from None
        except ValueError:
            raise AmapProviderError("高德坐标转换返回了无效数据。") from None

        if (
            not isinstance(payload, dict)
            or payload.get("status") != "1"
            or payload.get("infocode") != "10000"
        ):
            raise AmapProviderError("高德坐标转换失败，请稍后重试。")
        converted_coordinate = payload.get("locations")
        if not isinstance(converted_coordinate, str):
            raise AmapProviderError("高德坐标转换未返回有效坐标。")
        return normalize_coordinate(converted_coordinate)
