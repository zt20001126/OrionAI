"""验证高德 V5 步行规划的请求与错误转换。"""

import httpx
import pytest

from app.core.config import Settings
from app.modules.digital_human.providers.amap import walking
from app.modules.digital_human.providers.amap.client import AmapProviderError


def mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """以内存响应代替高德请求；调用方：路线客户端测试。"""
    client = httpx.AsyncClient
    monkeypatch.setattr(
        walking.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.anyio
async def test_walking_route_request_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/direction/walking"
        assert request.url.params["origin"] == "120.150000,30.280000"
        assert request.url.params["destination_id"] == "poi-1"
        assert request.url.params["show_fields"] == "cost,navi,polyline"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "infocode": "10000",
                "route": {
                    "paths": [
                        {
                            "distance": "1050",
                            "cost": {"duration": "780"},
                            "steps": [
                                {
                                    "instruction": "向东步行",
                                    "step_distance": "300",
                                    "polyline": "120,30;121,30",
                                }
                            ],
                        }
                    ]
                },
            },
        )

    mock_transport(monkeypatch, respond)
    client = walking.AmapWalkingRouteClient(Settings(_env_file=None, amap_api_key="test-key"))
    result = await client.plan("120.15,30.28", "120.158,30.284", "poi-1")
    assert result["distance_m"] == 1050
    assert result["duration_s"] == 780
    assert result["steps"][0]["distance_m"] == 300


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"status": "0", "infocode": "10001"},
        {"status": "1", "infocode": "10000", "route": {"paths": []}},
        {"status": "1", "infocode": "10000", "route": {"paths": [{}]}},
    ],
)
async def test_walking_route_invalid_response(
    monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
    client = walking.AmapWalkingRouteClient(Settings(_env_file=None, amap_api_key="test-key"))
    with pytest.raises(AmapProviderError):
        await client.plan("120,30", "121,31")


@pytest.mark.anyio
async def test_walking_route_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    mock_transport(monkeypatch, timeout)
    client = walking.AmapWalkingRouteClient(Settings(_env_file=None, amap_api_key="test-key"))
    with pytest.raises(AmapProviderError, match="超时"):
        await client.plan("120,30", "121,31")


@pytest.mark.parametrize("coordinate", ["", "181,0", "0,91", "nan,0", "1,2,3"])
def test_invalid_coordinate(coordinate: str) -> None:
    with pytest.raises(AmapProviderError):
        walking.normalize_coordinate(coordinate)


@pytest.mark.anyio
async def test_convert_browser_gps_to_gcj02(monkeypatch: pytest.MonkeyPatch) -> None:
    """浏览器 WGS-84 坐标必须经过高德转换后用于算路。"""

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/assistant/coordinate/convert"
        assert request.url.params["coordsys"] == "gps"
        assert request.url.params["locations"] == "120.150000,30.280000"
        return httpx.Response(
            200, json={"status": "1", "infocode": "10000", "locations": "120.154,30.282"}
        )

    mock_transport(monkeypatch, respond)
    client = walking.AmapWalkingRouteClient(Settings(_env_file=None, amap_api_key="test-key"))
    assert await client.convert_gps("120.15,30.28") == "120.154000,30.282000"
