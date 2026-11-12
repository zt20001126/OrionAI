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


def get_authorized_browser_location(config: RunnableConfig) -> tuple[float, float]:
    """读取本轮已授权的浏览器经纬度；输入 config，输出经度和纬度；调用方：数字人路线工具。"""
    configurable: dict[str, Any] = dict((config or {}).get("configurable") or {})
    resume_answers = configurable.get("resume_answers")
    consent_answer = (
        resume_answers.get(DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID)
        if isinstance(resume_answers, dict)
        else None
    )
    if consent_answer != DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER:
        raise AmapProviderError("路线起点使用当前位置前，需要先征求浏览器定位授权。")

    latitude, longitude, _accuracy = _validated_browser_location(configurable.get("user_location"))
    return longitude, latitude


def _validated_browser_location(user_location: object) -> tuple[float, float, float]:
    """校验设备定位字段；输入本轮位置上下文，输出纬度、经度及精度；调用方：数字人位置工具。"""
    if not isinstance(user_location, dict) or user_location.get("status") != "granted":
        raise AmapProviderError("浏览器未能提供当前位置，请询问用户填写起点地址。")

    latitude = user_location.get("latitude")
    longitude = user_location.get("longitude")
    accuracy = user_location.get("accuracy_meters")
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        for value in (latitude, longitude, accuracy)
    ):
        raise AmapProviderError("浏览器定位数据无效，请询问用户填写起点地址。")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and accuracy >= 0):
        raise AmapProviderError("浏览器定位坐标超出有效范围。")
    return latitude, longitude, accuracy


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
        try:
            latitude, longitude, accuracy = _validated_browser_location(user_location)
        except AmapProviderError as error:
            return json.dumps(
                {"success": False, "message": str(error)},
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
