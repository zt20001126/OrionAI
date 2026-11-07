"""调用淘客易商品搜索与详情 API。"""

from typing import Any

import httpx

from app.core.config import Settings, get_settings

REQUEST_TIMEOUT_SECONDS = 15.0
PRODUCT_FIELDS = (
    "goodsid", "itemid", "title", "description", "mainimage", "images", "itemlink",
    "categoryid", "originalprice", "price", "couponamount", "couponlink", "validuntil",
    "monthsales", "dailysales", "twohoursales",
)


class TkyProviderError(Exception):
    """淘客易调用失败时可安全交给数字人模型的错误。"""


class TkyClient:
    """封装淘客易鉴权、请求和商品字段提取。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """保存服务端 TKY 配置；由数字人商品工具创建。"""
        self._settings = settings or get_settings()

    async def search_goods(self, params: dict[str, str | int | float]) -> dict[str, Any]:
        """查询一页商品；输入已校验筛选参数，输出精简结果和分页信息。"""
        payload = await self._request("GET", "/goods", params=params)
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise TkyProviderError("商品服务返回的数据格式无效，请稍后重试。")
        items = [self._select_product(item) for item in data["items"] if isinstance(item, dict)]
        return {
            "items": items,
            "page": params.get("page", 1),
            "size": params.get("size", 20),
            "hasmore": data.get("hasmore"),
        }

    async def get_goods_detail(self, goodsid: int) -> dict[str, Any]:
        """按淘客易商品记录 ID 查询详情；输出接口实际提供的商品字段。"""
        payload = await self._request("GET", f"/goods/{goodsid}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise TkyProviderError("商品服务返回的详情格式无效，请稍后重试。")
        return self._select_product(data)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float] | None = None,
    ) -> dict[str, Any]:
        """请求 TKY 并将上游状态映射为不含凭据的错误提示。"""
        token = self._settings.tky_api_token.get_secret_value().strip()
        if not token:
            raise TkyProviderError("商品查询服务尚未配置，请联系管理员配置 TKY_API_TOKEN。")
        base_url = self._settings.tky_api_base_url.strip().rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.request(
                    method,
                    f"{base_url}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
        except httpx.TimeoutException:
            raise TkyProviderError("商品查询超时，请稍后重试。") from None
        except httpx.RequestError:
            raise TkyProviderError("暂时无法连接商品服务，请稍后重试。") from None

        if response.status_code == 401:
            raise TkyProviderError("商品服务认证失败，请联系管理员检查 TKY_API_TOKEN。")
        if response.status_code == 404:
            raise TkyProviderError("没有找到该商品记录，请确认商品是否仍然有效。")
        if response.status_code == 429:
            raise TkyProviderError("商品查询过于频繁或额度已用完，请稍后重试。")
        if response.status_code == 403:
            raise TkyProviderError("商品服务账号未开通所需权限，请联系管理员。")
        if response.status_code >= 500:
            raise TkyProviderError("商品服务暂时不可用，请稍后重试。")
        if response.is_error:
            raise TkyProviderError("商品查询参数未被服务接受，请检查条件后重试。")
        try:
            payload = response.json()
        except ValueError:
            raise TkyProviderError("商品服务返回了无法识别的数据，请稍后重试。") from None
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise TkyProviderError("商品服务未能完成查询，请稍后重试。")
        return payload

    @staticmethod
    def _select_product(product: dict[str, Any]) -> dict[str, Any]:
        """仅保留官方商品字段，避免将大段原始响应传给模型。"""
        return {field: product.get(field) for field in PRODUCT_FIELDS}
