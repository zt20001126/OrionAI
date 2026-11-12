"""高德地图服务 Provider。"""

from app.modules.digital_human.providers.amap.client import (
    AmapIpLocation,
    AmapIpLocationClient,
    AmapProviderError,
)
from app.modules.digital_human.providers.amap.coordinates import AmapCoordinateClient
from app.modules.digital_human.providers.amap.geocoding import AmapGeocodingClient
from app.modules.digital_human.providers.amap.poi_client import AmapPoi, AmapPoiSearchClient
from app.modules.digital_human.providers.amap.route_planning import AmapRoutePlanningClient

__all__ = [
    "AmapIpLocation",
    "AmapIpLocationClient",
    "AmapCoordinateClient",
    "AmapGeocodingClient",
    "AmapPoi",
    "AmapPoiSearchClient",
    "AmapProviderError",
    "AmapRoutePlanningClient",
]
