"""提供数字人本轮设备位置读取及 IP 城市级回退工具。"""

import json
import logging
import math
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER,
    DIGITAL_HUMAN_LOCATION_CONSENT_IP_ANSWER,
    DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
)
from app.modules.digital_human.providers.amap import AmapIpLocationClient, AmapProviderError

logger = logging.getLogger(__name__)


@tool("get_user_location")
async def get_user_location(config: RunnableConfig) -> str:
    """读取用户本轮授权位置；输入为 Agent 运行配置，输出设备坐标或 IP 粗定位。"""
    configurable: dict[str, Any] = dict((config or {}).get("configurable") or {})
    resume_answers = configurable.get("resume_answers")
    consent_answer = (
        resume_answers.get(DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID)
        if isinstance(resume_answers, dict)
        else None
    )
    user_location = configurable.get("user_location")
    if isinstance(user_location, dict):
        if consent_answer != DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER:
            return json.dumps(
                {"success": False, "message": "当前授权不允许读取浏览器位置。"},
                ensure_ascii=False,
            )
        status = user_location.get("status")
        if status != "granted":
            return json.dumps(
                {
                    "success": False,
                    "status": status,
                    "message": "浏览器未能提供当前位置，请询问用户区县、商圈或地址。",
                },
                ensure_ascii=False,
            )

        latitude = user_location.get("latitude")
        longitude = user_location.get("longitude")
        accuracy = user_location.get("accuracy_meters")
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            for value in (latitude, longitude, accuracy)
        ):
            return json.dumps(
                {"success": False, "message": "浏览器定位数据无效，请询问用户提供位置。"},
                ensure_ascii=False,
            )
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and accuracy >= 0):
            return json.dumps(
                {"success": False, "message": "浏览器定位坐标超出有效范围。"},
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "success": True,
                "source": "browser_geolocation",
                "coordinate_system": "WGS-84",
                "latitude": latitude,
                "longitude": longitude,
                "accuracy_meters": accuracy,
            },
            ensure_ascii=False,
        )

    if consent_answer == DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER:
        return json.dumps(
            {
                "success": False,
                "message": "浏览器没有返回设备坐标，请询问用户区县、商圈或地址。",
            },
            ensure_ascii=False,
        )
    if (
        isinstance(resume_answers, dict)
        and DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID in resume_answers
        and consent_answer != DIGITAL_HUMAN_LOCATION_CONSENT_IP_ANSWER
    ):
        return json.dumps(
            {
                "success": False,
                "message": "用户未同意位置查询，请尊重选择并询问用户提供区县、商圈或地址。",
            },
            ensure_ascii=False,
        )

    client_ip = configurable.get("client_ip")
    try:
        location = await AmapIpLocationClient().locate(
            client_ip if isinstance(client_ip, str) else None
        )
    except AmapProviderError as error:
        logger.warning("digital_human_location_lookup_failed reason=%s", str(error))
        return json.dumps(
            {
                "province": "",
                "city": "",
                "adcode": "",
                "success": False,
                "message": str(error),
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "province": location.province,
            "city": location.city,
            "adcode": location.adcode,
            "success": True,
        },
        ensure_ascii=False,
    )
