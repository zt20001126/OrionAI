"""数字人助手的淘客易商品搜索和详情工具。"""

import json
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.digital_human.providers.tky import TkyClient, TkyProviderError

SortOrder = Literal["latest", "price_asc", "price_desc", "daily_sales", "two_hour_sales"]


class SearchProductsInput(BaseModel):
    """商品搜索筛选参数。"""

    model_config = ConfigDict(extra="forbid")

    keyword: str | None = Field(default=None, max_length=60)
    category: int | None = None
    minprice: float | None = Field(default=None, ge=0)
    maxprice: float | None = Field(default=None, ge=0)
    sort: SortOrder = "latest"
    page: int = Field(default=1, ge=1, le=1000)
    size: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_price_range(self) -> "SearchProductsInput":
        """确保价格筛选区间有效；由工具参数解析调用。"""
        if self.minprice is not None and self.maxprice is not None:
            if self.minprice > self.maxprice:
                raise ValueError("最低价不能大于最高价。")
        return self


class GetProductDetailInput(BaseModel):
    """淘客易商品记录 ID。"""

    model_config = ConfigDict(extra="forbid")

    goodsid: int = Field(gt=0, description="淘客易内部商品记录 ID，不是淘宝商品 ID")


@tool(args_schema=SearchProductsInput)
async def search_products(
    keyword: str | None = None,
    category: int | None = None,
    minprice: float | None = None,
    maxprice: float | None = None,
    sort: SortOrder = "latest",
    page: int = 1,
    size: int = 20,
) -> str:
    """按关键词和可选条件搜索淘宝商品；只依据返回数据介绍商品。"""
    params: dict[str, str | int | float] = {"sort": sort, "page": page, "size": size}
    if keyword is not None and keyword.strip():
        params["keyword"] = keyword.strip()
    if category is not None:
        params["category"] = category
    if minprice is not None:
        params["minprice"] = minprice
    if maxprice is not None:
        params["maxprice"] = maxprice
    try:
        result = await TkyClient().search_goods(params)
    except TkyProviderError as error:
        result = {"status": "error", "message": str(error)}
    if result.get("items") == []:
        result["message"] = "没有找到符合条件的商品。"
    return json.dumps(result, ensure_ascii=False)


@tool(args_schema=GetProductDetailInput)
async def get_product_detail(goodsid: int) -> str:
    """查询淘客易商品记录详情；goodsid 来自商品搜索结果。"""
    try:
        result = await TkyClient().get_goods_detail(goodsid)
        result = {"status": "success", "product": result}
    except TkyProviderError as error:
        result = {"status": "error", "message": str(error)}
    return json.dumps(result, ensure_ascii=False)
