import pytest
from pydantic import ValidationError

from app.modules.conversations.schemas.schemas import (
    ConversationKlineChartEvent,
    KlineChartContentPart,
    MessageContent,
)


def _chart_payload() -> dict[str, object]:
    return {
        "code": "600519",
        "name": "贵州茅台",
        "period": "daily",
        "adjust": "qfq",
        "start_date": "2026-11-10",
        "end_date": "2026-11-10",
        "source": "AKShare",
        "candles": [
            {
                "date": "2026-11-10",
                "open": 10,
                "close": 11,
                "high": 12,
                "low": 9,
                "volume": 100,
            }
        ],
    }


def test_kline_event_and_history_part_share_the_content_contract() -> None:
    payload = _chart_payload()
    event = ConversationKlineChartEvent(type="kline_chart", content=payload)
    content = MessageContent.model_validate(
        {"parts": [KlineChartContentPart(type="kline_chart", content=payload).model_dump()]}
    )

    assert event.model_dump(mode="json")["type"] == "kline_chart"
    assert event.model_dump(mode="json")["content"]["candles"][0]["close"] == 11
    assert content.parts[0].type == "kline_chart"


def test_kline_payload_rejects_invalid_ohlc_and_unsorted_dates() -> None:
    payload = _chart_payload()
    payload["candles"] = [
        {
            "date": "2026-11-10",
            "open": 10,
            "close": 11,
            "high": 10.5,
            "low": 9,
            "volume": 100,
        }
    ]
    with pytest.raises(ValidationError):
        ConversationKlineChartEvent(type="kline_chart", content=payload)
