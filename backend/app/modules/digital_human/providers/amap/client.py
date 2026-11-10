"""封装高德 IP 定位 Web 服务的异步调用。"""

from dataclasses import dataclass
from ipaddress import IPv4Address, ip_address

import httpx

from app.core.config import Settings, get_settings

AMAP_IP_LOCATION_URL = "https://restapi.amap.com/v3/ip"
REQUEST_TIMEOUT_SECONDS = 5.0


class AmapProviderError(Exception):
    """可安全交给数字人工具层处理的高德定位错误。"""


@dataclass(frozen=True)
class AmapIpLocation:
    """高德 IP 定位返回的省份、城市和行政区划码。"""

    province: str
    city: str
    adcode: str


class AmapIpLocationClient:
    """调用高德 v3 IP 定位接口并校验可用位置结果。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """保存高德服务配置；调用方为数字人定位工具。"""
        self._settings = settings or get_settings()

    async def locate(self, client_ip: str | None) -> AmapIpLocation:
        """按当前请求的公网 IPv4 查询位置；输入无效或上游不可用时抛出安全错误。"""
        normalized_ip = _public_ipv4(client_ip)
        if normalized_ip is None:
            raise AmapProviderError("当前请求未提供可用于定位的公网 IPv4 地址。")

        api_key = self._settings.amap_api_key.get_secret_value().strip()
        if not api_key:
            raise AmapProviderError("定位服务尚未配置，请联系管理员。")

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    AMAP_IP_LOCATION_URL,
                    params={"key": api_key, "ip": normalized_ip, "output": "json"},
                )
        except httpx.TimeoutException:
            raise AmapProviderError("IP 定位请求超时，请稍后重试。") from None
        except httpx.RequestError:
            raise AmapProviderError("暂时无法连接 IP 定位服务，请稍后重试。") from None

        if response.is_error:
            raise AmapProviderError("IP 定位服务暂时不可用，请稍后重试。")

        try:
            payload = response.json()
        except ValueError:
            raise AmapProviderError("IP 定位服务返回了无法识别的数据。") from None

        if not isinstance(payload, dict) or payload.get("status") != "1":
            raise AmapProviderError("IP 定位服务未能完成查询。")

        province = _text_field(payload, "province")
        city = _text_field(payload, "city")
        adcode = _text_field(payload, "adcode")
        if province == "局域网" or not (province or city):
            raise AmapProviderError("高德未能识别当前 IP 的省份或城市。")

        return AmapIpLocation(province=province, city=city, adcode=adcode)


def _public_ipv4(value: str | None) -> str | None:
    """只接受高德 v3 支持的公网 IPv4，避免把内网或服务器地址传给上游。"""
    if value is None:
        return None
    try:
        parsed = ip_address(value)
    except ValueError:
        return None
    if not isinstance(parsed, IPv4Address) or not parsed.is_global:
        return None
    return str(parsed)


def _text_field(payload: dict[str, object], name: str) -> str:
    """读取高德响应中的可选文本字段，并去掉外围空白。"""
    value = payload.get(name)
    return value.strip() if isinstance(value, str) else ""
