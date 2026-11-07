"""淘客易商品 API Provider。"""

from app.modules.digital_human.providers.tky.client import TkyClient, TkyProviderError

__all__ = ["TkyClient", "TkyProviderError"]
