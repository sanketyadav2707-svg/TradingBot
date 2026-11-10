from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tradingbot.api.app import create_app
from tradingbot.api.runtime import DashboardRuntime
from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperBroker


def _client() -> TestClient:
    return TestClient(create_app(DashboardRuntime.from_config()))


def test_health_reports_api_process_not_trading_readiness() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]
    assert payload["timestamp"].endswith("Z")


def test_summary_does_not_fabricate_account_or_market_state() -> None:
    payload = _client().get("/api/v1/dashboard/summary").json()
    assert payload["meta"]["environment"] == "DISCONNECTED"
    assert all(value is None for value in payload["account"].values())
    assert payload["strategy"] == {"name": None, "state": "UNKNOWN"}
    assert payload["market_data"] == {
        "connection": "DISCONNECTED",
        "last_update": None,
        "symbols": [],
    }


def test_instruments_are_loaded_from_repository_configuration() -> None:
    response = _client().get("/api/v1/instruments")
    assert response.status_code == 200
    payload = response.json()
    assert payload["availability"] == "AVAILABLE"
    mes = next(item for item in payload["items"] if item["symbol"] == "MES")
    assert mes["tick_size"] == "0.25"
    assert mes["tick_value_usd"] == {"amount": "1.25", "currency": "USD"}


def test_risk_snapshot_exposes_limits_but_not_unmeasured_usage() -> None:
    payload = _client().get("/api/v1/risk/snapshot").json()
    assert payload["gate"] == "UNKNOWN"
    assert payload["daily_loss_limit"] == {"amount": "300.00", "currency": "USD"}
    assert payload["daily_loss_used"] is None
    assert payload["open_positions"] is None
    assert payload["max_contracts"] == 1
    assert "account_snapshot_unavailable" in payload["reasons"]


def test_unavailable_ledgers_are_explicit() -> None:
    client = _client()
    positions = client.get("/api/v1/positions").json()
    trades = client.get("/api/v1/trades").json()
    equity = client.get("/api/v1/performance/equity").json()
    events = client.get("/api/v1/events").json()
    assert positions["availability"] == "NOT_IMPLEMENTED"
    assert trades["availability"] == "NOT_PERSISTED"
    assert equity["availability"] == "NOT_PERSISTED"
    assert events["availability"] == "NOT_IMPLEMENTED"
    assert positions["items"] == trades["items"] == equity["items"] == events["items"] == []


def test_paper_fills_are_read_only_and_require_an_injected_broker() -> None:
    client = _client()
    assert client.get("/api/v1/paper/fills").json()["availability"] == "NOT_CONFIGURED"

    broker = PaperBroker(Instrument("MES", 0.25, 1.25, 5.0), slippage_ticks_per_side=1)
    broker.submit_market(
        side=Side.LONG,
        quantity=1,
        reference_price=6000,
        timestamp=datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc),
    )
    runtime = DashboardRuntime.from_config()
    runtime.paper_broker = broker
    payload = TestClient(create_app(runtime)).get("/api/v1/paper/fills").json()
    assert payload["availability"] == "AVAILABLE"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["fill_price"] == "6000.25"
    assert payload["items"][0]["side"] == "LONG"


def test_cors_allows_only_local_dashboard_origin() -> None:
    client = _client()
    allowed = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"

    rejected = client.options(
        "/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_api_exposes_no_mutation_routes() -> None:
    schema = _client().get("/openapi.json").json()
    for operations in schema["paths"].values():
        assert set(operations).issubset({"get"})


def test_pagination_rejects_invalid_cursors() -> None:
    assert _client().get("/api/v1/trades?limit=101").status_code == 422
    assert _client().get("/api/v1/trades?cursor=-1").status_code == 400
    assert _client().get("/api/v1/events?cursor=abc").status_code == 400
