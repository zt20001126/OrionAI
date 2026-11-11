"""封装高德 POI 2.0 周边搜索 Web 服务。"""

from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.modules.digital_human.providers.amap.client import AmapProviderError

AMAP_POI_AROUND_URL = "https://restapi.amap.com/v5/place/around"
AMAP_POI_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class AmapPoi:
    """周边搜索返回的商家摘要，供数字人工具整理给用户。"""

    name: str
    address: str
    location: str
    distance_meters: str


class AmapPoiSearchClient:
    """按坐标、关键词和半径调用高德 POI 2.0 周边搜索。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """读取高德 Web 服务密钥；调用方为数字人周边搜索工具。"""
        self._settings = settings or get_settings()

    async def search_around(
        self, *, longitude: float, latitude: float, keyword: str, radius_meters: int
    ) -> list[AmapPoi]:
        """查询指定中心点周边 POI；输入搜索条件，输出距离排序的商家摘要。"""
        api_key = self._settings.amap_api_key.get_secret_value().strip()
        if not api_key:
            raise AmapProviderError("周边搜索服务尚未配置，请联系管理员。")

        params = {
            "key": api_key,
            "location": f"{longitude:.6f},{latitude:.6f}",
            "keywords": keyword,
            "radius": radius_meters,
            "sortrule": "distance",
            "page_size": 10,
            "page_num": 1,
            "show_fields": "business",
        }
        try:
            async with httpx.AsyncClient(timeout=AMAP_POI_TIMEOUT_SECONDS) as client:
                response = await client.get(AMAP_POI_AROUND_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            raise AmapProviderError("高德周边搜索超时，请稍后重试。") from None
        except httpx.RequestError:
            raise AmapProviderError("暂时无法连接高德周边搜索服务。") from None
        except ValueError:
            raise AmapProviderError("高德周边搜索返回了无法识别的数据。") from None

        if payload.get("status") != "1":
            raise AmapProviderError("高德周边搜索未能完成查询。")

        return [
            AmapPoi(
                name=poi["name"],
                address=poi.get("address", ""),
                location=poi["location"],
                distance_meters=poi.get("distance", ""),
            )
            for poi in payload.get("pois", [])
        ]
