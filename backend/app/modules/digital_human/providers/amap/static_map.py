"""调用高德静态地图服务，将已规划的步行路线渲染为图片。"""

import math
from collections.abc import Sequence

import httpx

from app.core.config import Settings, get_settings
from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.walking import normalize_coordinate

STATIC_MAP_URL = "https://restapi.amap.com/v3/staticmap"
STATIC_MAP_TIMEOUT_SECONDS = 8.0
# 高德未公布 GET URL 长度上限；预览图请求采用保守上限，超出时简化路线点。
STATIC_MAP_MAX_URL_LENGTH = 7_000
STATIC_MAP_SIZE = "750*260"
ROUTE_SIMPLIFICATION_TOLERANCES_METERS = (5.0, 15.0, 30.0)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
STATIC_MAP_IMAGE_SIGNATURES = {
    "image/png": PNG_SIGNATURE,
    "image/jpeg": JPEG_SIGNATURE,
}


class AmapStaticMapClient:
    """使用服务端高德 Key 生成步行路线静态图片。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """读取高德服务配置；调用方：会话路线地图服务。"""
        self._settings = settings or get_settings()

    async def render_route(
        self,
        origin: str,
        destination: str,
        step_polylines: Sequence[str | None],
    ) -> tuple[bytes, str]:
        """生成带路线和起终点标记的地图图片；输入路线端点和分段坐标；输出图片字节及 MIME 类型。

        调用方：ConversationService 的路线图片接口。路线点过多时仅简化地图预览，
        不改变已保存的导航步骤或路线数据。
        """
        api_key = self._settings.amap_api_key.get_secret_value().strip()
        if not api_key:
            raise AmapProviderError("静态地图服务尚未配置，请联系管理员。")

        normalized_origin = normalize_coordinate(origin)
        normalized_destination = normalize_coordinate(destination)
        route_points = _merge_route_points(step_polylines)

        try:
            async with httpx.AsyncClient(timeout=STATIC_MAP_TIMEOUT_SECONDS) as client:
                request = _build_short_request(
                    client,
                    api_key,
                    normalized_origin,
                    normalized_destination,
                    route_points,
                )
                response = await client.send(request)
                response.raise_for_status()
        except httpx.TimeoutException:
            raise AmapProviderError("静态地图请求超时，请稍后重试。") from None
        except httpx.HTTPError:
            raise AmapProviderError("暂时无法连接高德静态地图服务。") from None

        content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0]
        content_type = content_type.strip().lower()
        if content_type not in STATIC_MAP_IMAGE_SIGNATURES or not response.content.startswith(
            STATIC_MAP_IMAGE_SIGNATURES[content_type]
        ):
            raise AmapProviderError("高德静态地图服务未返回有效图片。")
        return response.content, content_type


def _merge_route_points(step_polylines: Sequence[str | None]) -> list[str]:
    """合并并校验导航轨迹。

    输入：每步路线坐标串；输出：按路线顺序排列且去除相邻重复点的坐标；
    调用方：静态地图客户端。任何步骤缺少坐标时拒绝绘制不完整路线。
    """
    if not step_polylines or any(not polyline for polyline in step_polylines):
        raise AmapProviderError("路线缺少完整轨迹坐标，暂时无法生成地图。")

    route_points: list[str] = []
    for polyline in step_polylines:
        for raw_coordinate in polyline.split(";"):
            coordinate = normalize_coordinate(raw_coordinate)
            if not route_points or route_points[-1] != coordinate:
                route_points.append(coordinate)

    if len(route_points) < 2:
        raise AmapProviderError("路线轨迹坐标不足，暂时无法生成地图。")
    return route_points


def _static_map_params(
    api_key: str,
    origin: str,
    destination: str,
    route_points: Sequence[str],
) -> dict[str, str]:
    """构造高德静态地图请求参数。

    输入：后端 Key、路线端点及合并后的路线点；输出：供 HTTP GET 编码的参数字典；
    调用方：静态地图客户端。
    """
    return {
        "key": api_key,
        "size": STATIC_MAP_SIZE,
        "scale": "2",
        "paths": f"8,0x2563EB,1,,:{';'.join(route_points)}",
        "markers": (
            f"mid,0x16A34A,起:{origin}|mid,0xDC2626,终:{destination}"
        ),
    }


def _build_short_request(
    client: httpx.AsyncClient,
    api_key: str,
    origin: str,
    destination: str,
    route_points: Sequence[str],
) -> httpx.Request:
    """构造 URL 长度受控的 GET 请求。

    输入：HTTP 客户端、路线端点和合并轨迹；输出：符合应用 URL 上限的请求；
    调用方：静态地图客户端。超限时逐步简化预览折线，原始消息路线保持不变。
    """
    for tolerance_meters in (None, *ROUTE_SIMPLIFICATION_TOLERANCES_METERS):
        points = (
            list(route_points)
            if tolerance_meters is None
            else _simplify_route_points(route_points, tolerance_meters)
        )
        request = client.build_request(
            "GET",
            STATIC_MAP_URL,
            params=_static_map_params(api_key, origin, destination, points),
        )
        if len(str(request.url)) <= STATIC_MAP_MAX_URL_LENGTH:
            return request
    raise AmapProviderError("路线坐标过多，暂时无法生成静态地图。")


def _simplify_route_points(points: Sequence[str], tolerance_meters: float) -> list[str]:
    """按米制偏差简化预览折线并保留首尾。

    输入：经纬度坐标和允许偏差；输出：保形后的子序列；调用方：超长静态地图请求。
    """
    if len(points) <= 2:
        return list(points)

    coordinates: list[tuple[float, float]] = []
    for point in points:
        longitude, latitude = point.split(",")
        coordinates.append((float(longitude), float(latitude)))
    mean_latitude = sum(latitude for _, latitude in coordinates) / len(coordinates)
    longitude_scale = 111_320 * math.cos(math.radians(mean_latitude))
    projected_points = [
        (longitude * longitude_scale, latitude * 111_320)
        for longitude, latitude in coordinates
    ]

    retained_indices = {0, len(points) - 1}
    pending_segments = [(0, len(points) - 1)]
    while pending_segments:
        start_index, end_index = pending_segments.pop()
        furthest_index = -1
        furthest_distance = tolerance_meters
        for index in range(start_index + 1, end_index):
            distance = _distance_to_segment(
                projected_points[index],
                projected_points[start_index],
                projected_points[end_index],
            )
            if distance > furthest_distance:
                furthest_index = index
                furthest_distance = distance

        if furthest_index >= 0:
            retained_indices.add(furthest_index)
            pending_segments.extend(
                ((start_index, furthest_index), (furthest_index, end_index))
            )

    return [points[index] for index in sorted(retained_indices)]


def _distance_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """计算平面点到线段的最短距离。

    输入：投影后的点及线段端点；输出：最短距离（米）；调用方：路线折线简化。
    """
    segment_x = end[0] - start[0]
    segment_y = end[1] - start[1]
    length_squared = segment_x * segment_x + segment_y * segment_y
    if length_squared == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])

    projection = (
        (point[0] - start[0]) * segment_x + (point[1] - start[1]) * segment_y
    ) / length_squared
    projection = min(1.0, max(0.0, projection))
    closest_x = start[0] + projection * segment_x
    closest_y = start[1] + projection * segment_y
    return math.hypot(point[0] - closest_x, point[1] - closest_y)
