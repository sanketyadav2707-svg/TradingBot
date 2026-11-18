from decimal import Decimal
from types import SimpleNamespace

import pytest

from tradingbot.execution.upstox_sandbox import (
    SandboxOrderRequest,
    UpstoxSandboxConfigurationError,
    UpstoxSandboxOrderClient,
)


class RequestModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeOrderApi:
    def __init__(self):
        self.calls = []

    def place_order(self, body):
        self.calls.append(("place", body))
        return {"status": "success", "data": {"order_ids": ["sbx-001"]}}

    def modify_order(self, body):
        self.calls.append(("modify", body))
        return {"status": "success", "data": {"order_id": "sbx-001"}}

    def cancel_order(self, order_id):
        self.calls.append(("cancel", order_id))
        return {"status": "success", "data": {"order_id": order_id}}


def make_client():
    sdk = SimpleNamespace(
        PlaceOrderV3Request=RequestModel,
        ModifyOrderRequest=RequestModel,
    )
    api = FakeOrderApi()
    return UpstoxSandboxOrderClient(order_api=api, sdk_module=sdk), api


def test_place_order_uses_v3_payload_and_disables_auto_slicing():
    client, api = make_client()
    result = client.place_order(
        SandboxOrderRequest(
            instrument_token="NSE_FO|12345",
            quantity=50,
            transaction_type="BUY",
            order_type="LIMIT",
            price=Decimal("125.50"),
        )
    )
    assert result["data"]["order_ids"] == ["sbx-001"]
    payload = api.calls[0][1].kwargs
    assert payload["instrument_token"] == "NSE_FO|12345"
    assert payload["quantity"] == 50
    assert payload["slice"] is False
    assert payload["market_protection"] == -1


def test_sandbox_client_supports_modify_and_cancel():
    client, api = make_client()
    client.modify_order(
        order_id="sbx-001",
        quantity=50,
        validity="DAY",
        price=Decimal("126"),
        order_type="LIMIT",
    )
    client.cancel_order(order_id="sbx-001")
    assert api.calls[0][0] == "modify"
    assert api.calls[0][1].kwargs["order_id"] == "sbx-001"
    assert api.calls[1] == ("cancel", "sbx-001")


@pytest.mark.parametrize(
    ("request", "message"),
    [
        (
            SandboxOrderRequest("NSE_EQ|INE123", 1, "BUY", price=Decimal("10")),
            "nse_fo",
        ),
        (
            SandboxOrderRequest("NSE_FO|123", 0, "BUY", price=Decimal("10")),
            "positive_integer",
        ),
        (
            SandboxOrderRequest("NSE_FO|123", 1, "BUY", price=Decimal("0")),
            "positive_price",
        ),
        (
            SandboxOrderRequest("NSE_FO|123", 1, "BUY", order_type="MARKET", market_protection=0),
            "market_protection",
        ),
    ],
)
def test_place_order_rejects_invalid_payload(request, message):
    client, api = make_client()
    with pytest.raises(ValueError, match=message):
        client.place_order(request)
    assert api.calls == []


def test_market_order_is_sandbox_only_and_requires_protection():
    client, api = make_client()
    client.place_order(
        SandboxOrderRequest(
            instrument_token="NSE_FO|123",
            quantity=50,
            transaction_type="SELL",
            order_type="MARKET",
            price=Decimal("0"),
            market_protection=-1,
        )
    )
    assert api.calls[0][0] == "place"


def test_missing_sandbox_token_is_rejected_before_sdk_import():
    with pytest.raises(UpstoxSandboxConfigurationError, match="sandbox_access_token_required"):
        UpstoxSandboxOrderClient.from_access_token(" ")

def test_factory_always_constructs_sdk_in_sandbox_mode(monkeypatch):
    import sys

    instances = {}

    class Configuration:
        def __init__(self, *, sandbox):
            instances["sandbox"] = sandbox
            self.access_token = None

    class ApiClient:
        def __init__(self, configuration):
            instances["configuration"] = configuration

    class OrderApiV3:
        def __init__(self, api_client):
            instances["api_client"] = api_client

    fake_sdk = SimpleNamespace(
        Configuration=Configuration,
        ApiClient=ApiClient,
        OrderApiV3=OrderApiV3,
        PlaceOrderV3Request=RequestModel,
        ModifyOrderRequest=RequestModel,
    )
    monkeypatch.setitem(sys.modules, "upstox_client", fake_sdk)
    client = UpstoxSandboxOrderClient.from_access_token("sandbox-token")
    assert isinstance(client, UpstoxSandboxOrderClient)
    assert instances["sandbox"] is True
    assert instances["configuration"].access_token == "sandbox-token"


def test_modify_order_rejects_invalid_limit_price_before_api_call():
    client, api = make_client()
    with pytest.raises(ValueError, match="limit_order_requires_positive_price"):
        client.modify_order(
            order_id="sbx-001",
            quantity=10,
            validity="DAY",
            price=Decimal("0"),
            order_type="LIMIT",
        )
    assert api.calls == []
