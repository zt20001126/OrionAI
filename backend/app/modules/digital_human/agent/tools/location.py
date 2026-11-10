"""提供基于当前请求公网 IP 的数字人位置查询工具。"""

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.modules.digital_human.providers.amap import AmapIpLocationClient, AmapProviderError

logger = logging.getLogger(__name__)


@tool("get_user_location")
async def get_user_location(config: RunnableConfig) -> str:
    """获取当前对话用户的大致省份和城市；不得查询他人 IP 或声称精确到街道门牌。"""
    configurable: dict[str, Any] = dict((config or {}).get("configurable") or {})
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
