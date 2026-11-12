"""封装高德地址和地标地理编码服务。"""

from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.coordinates import normalize_coordinate
from app.modules.digital_human.providers.amap.poi_client import AMAP_POI_TIMEOUT_SECONDS

AMAP_GEOCODING_URL = "https://restapi.amap.com/v3/geocode/geo"


@dataclass(frozen=True)
class AmapGeocodedLocation:
    """保存高德地理编码命中的唯一地点名称与 GCJ-02 坐标。"""

    name: str
    location: str


class AmapGeocodingClient:
    """将结构化地址或地标解析为高德路线 API 所需的坐标。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """读取高德服务配置；调用方：数字人路线规划 Provider。"""
        self._settings = settings or get_settings()

    async def geocode(self, address: str, city: str | None = None) -> AmapGeocodedLocation:
        """解析唯一地址或地标；输入文本及可选城市，输出 GCJ-02 地点；调用方：路线 Agent Tool。"""
        normalized_address = address.strip()
        if not normalized_address:
            raise AmapProviderError("路线起点或终点为空，请补充具体地址。")

        api_key = self._settings.amap_api_key.get_secret_value().strip()
        if not api_key:
            raise AmapProviderError("地址解析服务尚未配置，请联系管理员。")

        params = {"key": api_key, "address": normalized_address, "output": "json"}
        if city and city.strip():
            params["city"] = city.strip()
        try:
            async with httpx.AsyncClient(timeout=AMAP_POI_TIMEOUT_SECONDS) as client:
                response = await client.get(AMAP_GEOCODING_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            raise AmapProviderError("地址解析超时，请补充更具体的地址后重试。") from None
        except httpx.HTTPError:
            raise AmapProviderError("暂时无法连接高德地址解析服务。") from None
        except ValueError:
            raise AmapProviderError("高德地址解析返回了无法识别的数据。") from None

        if (
            not isinstance(payload, dict)
            or payload.get("status") != "1"
            or payload.get("infocode") != "10000"
        ):
            raise AmapProviderError("高德地址解析失败，请核对城市范围和地址格式后重试。")

        geocodes = payload.get("geocodes")
        if not isinstance(geocodes, list) or not geocodes:
            raise AmapProviderError(
                f"没有找到“{normalized_address}”的位置，请补充区县、路口、建筑物或出入口。"
            )
        if len(geocodes) != 1:
            raise AmapProviderError(
                f"“{normalized_address}”匹配到多个位置，请补充路口、门牌、建筑物或出入口。"
            )

        result = geocodes[0]
        if not isinstance(result, dict):
            raise AmapProviderError("高德地址解析返回了无效地点，请补充地址后重试。")
        location = result.get("location")
        if not isinstance(location, str):
            raise AmapProviderError("高德地址解析未返回有效坐标，请补充地址后重试。")
        formatted_address = result.get("formatted_address")
        name = (
            formatted_address.strip()
            if isinstance(formatted_address, str) and formatted_address.strip()
            else normalized_address
        )
        return AmapGeocodedLocation(name=name, location=normalize_coordinate(location))
