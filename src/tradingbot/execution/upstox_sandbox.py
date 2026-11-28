"""Upstox sandbox-only V3 order client.

This adapter can never target the live Upstox host: it creates the official SDK
with sandbox=True and exposes no live-mode switch. It is intentionally separate
from ExecutionRouter until sandbox semantics and account reconciliation are proven.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class UpstoxSandboxConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SandboxOrderRequest:
    instrument_token: str
    quantity: int
    transaction_type: str
    order_type: str = "LIMIT"
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    product: str = "I"
    validity: str = "DAY"
    tag: str = "tradingbot-sbx"
    disclosed_quantity: int = 0
    market_protection: int = -1


class UpstoxSandboxOrderClient:
    """V3 place/modify/cancel adapter pinned to Upstox sandbox SDK mode."""

    def __init__(self, *, order_api: Any, sdk_module: Any) -> None:
        if order_api is None or sdk_module is None:
            raise UpstoxSandboxConfigurationError("sandbox_sdk_and_order_api_required")
        self._order_api = order_api
        self._sdk = sdk_module

    @classmethod
    def from_access_token(cls, sandbox_access_token: str) -> "UpstoxSandboxOrderClient":
        if not isinstance(sandbox_access_token, str) or not sandbox_access_token.strip():
            raise UpstoxSandboxConfigurationError("sandbox_access_token_required")
        try:
            import upstox_client
        except ImportError as exc:
            raise UpstoxSandboxConfigurationError(
                "install_optional_dependency: pip install -e '.[upstox]'"
            ) from exc
        configuration = upstox_client.Configuration(sandbox=True)
        configuration.access_token = sandbox_access_token.strip()
        api_client = upstox_client.ApiClient(configuration)
        order_api = upstox_client.OrderApiV3(api_client)
        return cls(order_api=order_api, sdk_module=upstox_client)

    @staticmethod
    def _validate_order(request: SandboxOrderRequest) -> None:
        if not isinstance(request, SandboxOrderRequest):
            raise TypeError("sandbox_order_request_required")
        if not isinstance(request.instrument_token, str) or not request.instrument_token.startswith("NSE_FO|"):
            raise ValueError("sandbox_client_only_accepts_nse_fo_instrument_tokens")
        if type(request.quantity) is not int or request.quantity <= 0:
            raise ValueError("order_quantity_must_be_positive_integer")
        if request.transaction_type not in {"BUY", "SELL"}:
            raise ValueError("transaction_type_must_be_BUY_or_SELL")
        if request.order_type not in {"LIMIT", "MARKET", "SL", "SL-M"}:
            raise ValueError("unsupported_order_type")
        if request.product != "I":
            raise ValueError("only_intraday_product_is_enabled")
        if request.validity not in {"DAY", "IOC"}:
            raise ValueError("unsupported_order_validity")
        if not request.tag or len(request.tag) > 40:
            raise ValueError("order_tag_must_be_1_to_40_characters")
        if request.disclosed_quantity < 0:
            raise ValueError("disclosed_quantity_must_not_be_negative")
        if request.market_protection < -1 or request.market_protection > 25:
            raise ValueError("market_protection_out_of_range")
        price = Decimal(str(request.price))
        trigger = Decimal(str(request.trigger_price))
        if not price.is_finite() or not trigger.is_finite():
            raise ValueError("order_prices_must_be_finite")
        if request.order_type == "LIMIT" and price <= 0:
            raise ValueError("limit_order_requires_positive_price")
        if request.order_type in {"SL", "SL-M"} and trigger <= 0:
            raise ValueError("stop_order_requires_positive_trigger_price")
        if request.order_type == "MARKET" and request.market_protection == 0:
            raise ValueError("market_orders_require_market_protection")

    def place_order(self, request: SandboxOrderRequest) -> Any:
        self._validate_order(request)
        body = self._sdk.PlaceOrderV3Request(
            quantity=request.quantity,
            product=request.product,
            validity=request.validity,
            price=float(request.price),
            tag=request.tag,
            instrument_token=request.instrument_token,
            order_type=request.order_type,
            transaction_type=request.transaction_type,
            disclosed_quantity=request.disclosed_quantity,
            trigger_price=float(request.trigger_price),
            is_amo=False,
            slice=False,
            market_protection=request.market_protection,
        )
        return self._order_api.place_order(body)

    def modify_order(
        self,
        *,
        order_id: str,
        quantity: int,
        validity: str,
        price: Decimal,
        order_type: str,
        trigger_price: Decimal = Decimal("0"),
        disclosed_quantity: int = 0,
        market_protection: int = -1,
    ) -> Any:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("sandbox_order_id_required")
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("order_quantity_must_be_positive_integer")
        if validity not in {"DAY", "IOC"}:
            raise ValueError("unsupported_order_validity")
        if order_type not in {"LIMIT", "MARKET", "SL", "SL-M"}:
            raise ValueError("unsupported_order_type")
        price_value = Decimal(str(price))
        trigger_value = Decimal(str(trigger_price))
        if not price_value.is_finite() or not trigger_value.is_finite():
            raise ValueError("order_prices_must_be_finite")
        if order_type == "LIMIT" and price_value <= 0:
            raise ValueError("limit_order_requires_positive_price")
        if order_type in {"SL", "SL-M"} and trigger_value <= 0:
            raise ValueError("stop_order_requires_positive_trigger_price")
        if type(disclosed_quantity) is not int or disclosed_quantity < 0:
            raise ValueError("disclosed_quantity_must_be_non_negative_integer")
        if type(market_protection) is not int or not -1 <= market_protection <= 25:
            raise ValueError("market_protection_out_of_range")
        if order_type == "MARKET" and market_protection == 0:
            raise ValueError("market_orders_require_market_protection")
        body = self._sdk.ModifyOrderRequest(
            quantity=quantity,
            validity=validity,
            price=float(price),
            order_id=order_id.strip(),
            order_type=order_type,
            disclosed_quantity=disclosed_quantity,
            trigger_price=float(trigger_price),
            market_protection=market_protection,
        )
        return self._order_api.modify_order(body)

    def cancel_order(self, *, order_id: str) -> Any:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("sandbox_order_id_required")
        return self._order_api.cancel_order(order_id.strip())
