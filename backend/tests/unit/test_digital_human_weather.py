import json

import httpx
import pytest

from app.agent.schemas import QuestionPayload
from app.modules.digital_human.agent.tools import weather


def test_text_question_accepts_only_nonempty_bounded_answer() -> None:
    payload = QuestionPayload.model_validate(
        {"questions": [{"id": "location", "title": "你在哪个城市？", "type": "Text"}]}
    )
    payload.validate_answers({"location": "北京"})
    for answer in ("  ", "a" * 101):
        with pytest.raises(ValueError):
            payload.validate_answers({"location": answer})


@pytest.mark.anyio
async def test_weather_uses_location_and_returns_local_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={"results": [{
                "name": "北京", "country": "中国", "latitude": 39.9, "longitude": 116.4
            }]})
        assert request.url.params["timezone"] == "auto"
        return httpx.Response(200, json={
            "timezone": "Asia/Shanghai",
            "current": {"time": "2026-11-05T12:00", "temperature_2m": 20, "weather_code": 0},
            "current_units": {"temperature_2m": "°C"},
        })

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        weather.httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    result = json.loads(await weather.get_current_weather.ainvoke({"location": "北京"}))
    assert result["当地时间"] == "2026-11-05T12:00"
    assert result["当前天气"]["temperature_2m"] == 20
    assert result["天气现象"] == "晴"


@pytest.mark.anyio
async def test_weather_requests_clarification_for_ambiguous_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [
            {"name": "Springfield", "admin1": "Illinois", "country": "United States"},
            {"name": "Springfield", "admin1": "Massachusetts", "country": "United States"},
        ]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        weather.httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    result = json.loads(await weather.get_current_weather.ainvoke({"location": "Springfield"}))
    assert len(result["需要确认地点"]) == 2
