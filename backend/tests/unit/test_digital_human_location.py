import asyncio
import json
from collections.abc import Callable

import httpx
import pytest
from langchain_core.runnables import RunnableConfig

from app.core.config import Settings
from app.modules.digital_human.agent.tools import location
from app.modules.digital_human.providers.amap import (
    AmapIpLocation,
    AmapIpLocationClient,
    AmapProviderError,
)
from app.modules.digital_human.providers.amap import client as amap_client


def _mock_amap_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        amap_client.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )


def _settings() -> Settings:
    return Settings(_env_file=None, amap_api_key="test-amap-key")


@pytest.mark.anyio
async def test_amap_client_parses_domestic_location_and_sends_explicit_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/ip"
        assert request.url.params["key"] == "test-amap-key"
        assert request.url.params["ip"] == "114.247.50.2"
        assert request.url.params["output"] == "json"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "province": "北京市",
                "city": "北京市",
                "adcode": "110000",
            },
        )

    _mock_amap_transport(monkeypatch, respond)

    result = await AmapIpLocationClient(_settings()).locate("114.247.50.2")

    assert result == AmapIpLocation(province="北京市", city="北京市", adcode="110000")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "client_ip",
    [None, "not-an-ip", "127.0.0.1", "10.0.0.8", "192.168.1.2", "::1", "2001:4860:4860::8888"],
)
async def test_amap_client_rejects_unsupported_ip_without_request(
    monkeypatch: pytest.MonkeyPatch,
    client_ip: str | None,
) -> None:
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        pytest.fail("不支持的客户端 IP 不得请求高德")

    _mock_amap_transport(monkeypatch, unexpected_request)

    with pytest.raises(AmapProviderError):
        await AmapIpLocationClient(_settings()).locate(client_ip)


@pytest.mark.anyio
async def test_amap_client_rejects_overseas_response_without_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["ip"] == "8.8.8.8"
        return httpx.Response(
            200,
            json={"status": "1", "info": "OK", "province": "", "city": "", "adcode": ""},
        )

    _mock_amap_transport(monkeypatch, respond)

    with pytest.raises(AmapProviderError, match="未能识别"):
        await AmapIpLocationClient(_settings()).locate("8.8.8.8")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"status": "0", "info": "INVALID_USER_KEY"}),
        httpx.Response(429, json={"status": "0"}),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(
            200,
            json={"status": "1", "province": "局域网", "city": "", "adcode": ""},
        ),
    ],
)
async def test_amap_client_maps_api_and_response_failures_to_safe_errors(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
) -> None:
    _mock_amap_transport(monkeypatch, lambda _request: response)

    with pytest.raises(AmapProviderError):
        await AmapIpLocationClient(_settings()).locate("114.247.50.2")


@pytest.mark.anyio
async def test_amap_client_maps_timeout_without_exposing_request_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    _mock_amap_transport(monkeypatch, timeout)

    with pytest.raises(AmapProviderError, match="超时") as captured:
        await AmapIpLocationClient(_settings()).locate("114.247.50.2")

    assert "test-amap-key" not in str(captured.value)


@pytest.mark.anyio
async def test_location_tool_hides_ip_from_model_schema_and_reads_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_ips: list[str | None] = []

    async def locate(
        _client: AmapIpLocationClient,
        client_ip: str | None,
    ) -> AmapIpLocation:
        received_ips.append(client_ip)
        return AmapIpLocation(province="北京市", city="北京市", adcode="110000")

    monkeypatch.setattr(location.AmapIpLocationClient, "locate", locate)

    result = await location.get_user_location.ainvoke(
        {},
        config=RunnableConfig(
            configurable={"client_ip": "114.247.50.2"},
        ),
    )

    assert location.get_user_location.args == {}
    assert received_ips == ["114.247.50.2"]
    assert json.loads(result) == {
        "province": "北京市",
        "city": "北京市",
        "adcode": "110000",
        "success": True,
    }


@pytest.mark.anyio
async def test_location_tool_returns_failure_when_request_ip_is_missing() -> None:
    result = json.loads(await location.get_user_location.ainvoke({}, config={}))

    assert result["success"] is False
    assert result["province"] == result["city"] == result["adcode"] == ""
    assert "公网 IPv4" in result["message"]


@pytest.mark.anyio
async def test_concurrent_location_tool_calls_keep_request_ips_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_ips: list[str | None] = []

    async def locate(
        _client: AmapIpLocationClient,
        client_ip: str | None,
    ) -> AmapIpLocation:
        await asyncio.sleep(0)
        received_ips.append(client_ip)
        return AmapIpLocation(province="测试省", city="测试市", adcode="000000")

    monkeypatch.setattr(location.AmapIpLocationClient, "locate", locate)

    results = await asyncio.gather(
        location.get_user_location.ainvoke(
            {}, config={"configurable": {"client_ip": "114.247.50.2"}}
        ),
        location.get_user_location.ainvoke({}, config={"configurable": {"client_ip": "8.8.8.8"}}),
    )

    assert set(received_ips) == {"114.247.50.2", "8.8.8.8"}
    assert all(json.loads(result)["success"] is True for result in results)
