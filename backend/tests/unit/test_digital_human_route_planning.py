"""验证数字人多方式路线、高德地理编码和授权当前位置处理。"""

import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.modules.digital_human.agent.tools import route_planning as route_tool
from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER,
    DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
)
from app.modules.digital_human.providers.amap import geocoding, route_planning
from app.modules.digital_human.providers.amap.client import AmapProviderError


def mock_transport(monkeypatch: pytest.MonkeyPatch, module: Any, handler: Any) -> None:
    """用内存 HTTP 响应替代高德请求；调用方：路线与地理编码 Provider 测试。"""
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("mode", "expected_path"),
    [
        ("walking", "/v5/direction/walking"),
        ("cycling", "/v5/direction/bicycling"),
        ("driving", "/v5/direction/driving"),
    ],
)
async def test_route_client_dispatches_mode_and_normalizes_result(
    monkeypatch: pytest.MonkeyPatch,
    mode: route_planning.RouteMode,
    expected_path: str,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == expected_path
        assert request.url.params["origin"] == "120.150000,30.280000"
        assert request.url.params["destination"] == "120.160000,30.290000"
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
                                    "instruction": "沿西湖路前行",
                                    "step_distance": "300",
                                    "polyline": "120.15,30.28;120.16,30.29",
                                }
                            ],
                        }
                    ]
                },
            },
        )

    mock_transport(monkeypatch, route_planning, respond)
    client = route_planning.AmapRoutePlanningClient(
        Settings(_env_file=None, amap_api_key="test-key")
    )
    result = await client.plan(
        mode=mode,
        origin="120.15,30.28",
        destination="120.16,30.29",
        origin_name="我的位置",
        destination_name="西湖路",
    )

    assert result["mode"] == mode
    assert result["origin"] == {"name": "我的位置", "location": "120.150000,30.280000"}
    assert result["destination"]["name"] == "西湖路"
    assert result["distance_m"] == 1050
    assert result["duration_s"] == 780
    assert result["steps"][0]["distance_m"] == 300


@pytest.mark.anyio
async def test_route_client_rejects_invalid_coordinate() -> None:
    client = route_planning.AmapRoutePlanningClient(
        Settings(_env_file=None, amap_api_key="test-key")
    )
    with pytest.raises(AmapProviderError, match="坐标无效"):
        await client.plan(
            mode="cycling",
            origin="181,0",
            destination="120,30",
            origin_name="起点",
            destination_name="终点",
        )


@pytest.mark.anyio
async def test_geocoding_returns_unique_address_and_coordinate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/geocode/geo"
        assert request.url.params["address"] == "杭州市西湖区灵隐路"
        assert request.url.params["city"] == "杭州"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "infocode": "10000",
                "geocodes": [
                    {
                        "formatted_address": "浙江省杭州市西湖区灵隐路",
                        "location": "120.12,30.25",
                    }
                ],
            },
        )

    mock_transport(monkeypatch, geocoding, respond)
    client = geocoding.AmapGeocodingClient(Settings(_env_file=None, amap_api_key="test-key"))
    result = await client.geocode(" 杭州市西湖区灵隐路 ", city="杭州")

    assert result.name == "浙江省杭州市西湖区灵隐路"
    assert result.location == "120.120000,30.250000"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("geocodes", "expected_message"),
    [
        ([], "没有找到“西湖”"),
        ([{"location": "120,30"}, {"location": "121,31"}], "“西湖”匹配到多个位置"),
    ],
)
async def test_geocoding_requires_one_match(
    geocodes: list[dict[str, str]], expected_message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = geocoding.AmapGeocodingClient(Settings(_env_file=None, amap_api_key="test-key"))
    mock_transport(
        monkeypatch,
        geocoding,
        lambda _request: httpx.Response(
            200,
            json={"status": "1", "infocode": "10000", "geocodes": geocodes},
        ),
    )
    with pytest.raises(AmapProviderError, match=expected_message):
        await client.geocode("西湖")


@pytest.mark.anyio
async def test_route_tool_uses_only_authorized_browser_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    converted_coordinates: list[str] = []
    planned_modes: list[str] = []

    async def convert_gps(_self: object, coordinate: str) -> str:
        converted_coordinates.append(coordinate)
        return "120.151000,30.281000"

    async def geocode(_self: object, address: str, city: str | None = None):
        assert address == "杭州西湖"
        assert city is None
        return geocoding.AmapGeocodedLocation(name="杭州西湖", location="120.160000,30.290000")

    async def plan(
        _self: object,
        mode: str,
        origin: str,
        destination: str,
        origin_name: str,
        destination_name: str,
    ) -> dict[str, Any]:
        planned_modes.append(mode)
        return {
            "mode": mode,
            "origin": {"name": origin_name, "location": origin},
            "destination": {"name": destination_name, "location": destination},
            "distance_m": 500,
            "duration_s": 200,
            "steps": [{"instruction": "向西行驶", "distance_m": 500, "polyline": None}],
        }

    monkeypatch.setattr(route_tool.AmapCoordinateClient, "convert_gps", convert_gps)
    monkeypatch.setattr(route_tool.AmapGeocodingClient, "geocode", geocode)
    monkeypatch.setattr(route_tool.AmapRoutePlanningClient, "plan", plan)

    result = await route_tool.plan_route.ainvoke(
        {"mode": "cycling", "origin": "当前位置", "destination": "杭州西湖"},
        config={
            "configurable": {
                "resume_answers": {
                    DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID: (
                        DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER
                    )
                },
                "user_location": {
                    "status": "granted",
                    "latitude": 30.28,
                    "longitude": 120.15,
                    "accuracy_meters": 20,
                },
            }
        },
    )

    response = json.loads(result)
    assert response["success"] is True
    assert response["route"]["origin"]["name"] == "我的位置"
    assert converted_coordinates == ["120.15,30.28"]
    assert planned_modes == ["cycling"]


@pytest.mark.anyio
async def test_route_tool_rejects_current_location_without_consent() -> None:
    result = await route_tool.plan_route.ainvoke(
        {"mode": "walking", "origin": "当前位置", "destination": "杭州西湖"},
        config={"configurable": {}},
    )

    response = json.loads(result)
    assert response["success"] is False
    assert "授权" in response["message"]


@pytest.mark.anyio
async def test_route_tool_passes_user_city_to_both_address_lookups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geocoding_requests: list[tuple[str, str | None]] = []

    async def geocode(_self: object, address: str, city: str | None = None):
        geocoding_requests.append((address, city))
        return geocoding.AmapGeocodedLocation(name=address, location="120.15,30.28")

    async def plan(
        _self: object,
        mode: str,
        origin: str,
        destination: str,
        origin_name: str,
        destination_name: str,
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "origin": {"name": origin_name, "location": origin},
            "destination": {"name": destination_name, "location": destination},
            "distance_m": 1000,
            "duration_s": 600,
            "steps": [{"instruction": "沿道路前行", "distance_m": 1000, "polyline": None}],
        }

    monkeypatch.setattr(route_tool.AmapGeocodingClient, "geocode", geocode)
    monkeypatch.setattr(route_tool.AmapRoutePlanningClient, "plan", plan)

    result = await route_tool.plan_route.ainvoke(
        {
            "mode": "driving",
            "origin": "杭州市西湖区灵隐路",
            "destination": "杭州东站",
            "city": "杭州市",
        }
    )

    assert json.loads(result)["success"] is True
    assert geocoding_requests == [
        ("杭州市西湖区灵隐路", "杭州市"),
        ("杭州东站", "杭州市"),
    ]
