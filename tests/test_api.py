from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from tradingbot.api.app import create_app
from tradingbot.api.runtime import DashboardRuntime
from tradingbot.models import Instrument, Side
from tradingbot.execution.router import OrderIntent


MES = Instrument("MES", 0.25, 1.25, 5.0)
T0 = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)


def _client(tmp_path) -> TestClient:
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "account.sqlite3")
    return TestClient(create_app(runtime))


def _submit_research_paper_fill(runtime, side: Side, reference_price: float, timestamp: datetime):
    """Explicit research-only test path; production default requires a verified firm profile."""
    router = runtime.paper_engine.router_for(MES, require_firm_profile=False)
    runtime.account_store.mark_to_market({"MES": reference_price}, timestamp)
    return router.submit_entry(
        OrderIntent(
            instrument=MES,
            side=side,
            stop_ticks=8,
            reference_price=reference_price,
            timestamp=timestamp,
        )
    )


def test_health_reports_api_process_not_trading_readiness(tmp_path) -> None:
    response = _client(tmp_path).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]
    assert payload["timestamp"].endswith("Z")


def test_summary_reports_a_real_persistent_virtual_paper_account(tmp_path) -> None:
    payload = _client(tmp_path).get("/api/v1/dashboard/summary").json()
    assert payload["meta"]["environment"] == "PAPER"
    assert payload["meta"]["source"] == "sqlite-paper-account"
    assert payload["account"]["balance"] == {"amount": "50000.00", "currency": "USD"}
    assert payload["account"]["equity"] == {"amount": "50000.00", "currency": "USD"}
    assert payload["account"]["realized_pnl"] == {"amount": "0.00", "currency": "USD"}
    assert payload["account"]["unrealized_pnl"] == {"amount": "0.00", "currency": "USD"}
    assert payload["account"]["net_pnl"] == {"amount": "0.00", "currency": "USD"}
    assert payload["strategy"] == {"name": None, "state": "UNKNOWN"}
    assert payload["market_data"] == {
        "connection": "DISCONNECTED",
        "last_update": None,
        "symbols": [],
    }


def test_instruments_are_loaded_from_repository_configuration(tmp_path) -> None:
    response = _client(tmp_path).get("/api/v1/instruments")
    assert response.status_code == 200
    payload = response.json()
    assert payload["availability"] == "AVAILABLE"
    mes = next(item for item in payload["items"] if item["symbol"] == "MES")
    assert mes["tick_size"] == "0.25"
    assert mes["tick_value_usd"] == {"amount": "1.25", "currency": "USD"}


def test_risk_snapshot_exposes_limits_but_keeps_gate_unknown(tmp_path) -> None:
    payload = _client(tmp_path).get("/api/v1/risk/snapshot").json()
    assert payload["gate"] == "UNKNOWN"
    assert payload["daily_loss_limit"] == {"amount": "300.00", "currency": "USD"}
    assert payload["daily_loss_used"] is None
    assert payload["open_positions"] == 0
    assert payload["max_contracts"] == 1
    assert "risk_gate_has_not_been_evaluated_for_a_running_strategy_session" in payload["reasons"]


def test_empty_persistent_ledgers_are_available_not_missing(tmp_path) -> None:
    client = _client(tmp_path)
    positions = client.get("/api/v1/positions").json()
    trades = client.get("/api/v1/trades").json()
    equity = client.get("/api/v1/performance/equity").json()
    events = client.get("/api/v1/events").json()
    assert positions["availability"] == "AVAILABLE"
    assert positions["items"] == []
    assert trades["availability"] == "AVAILABLE"
    assert trades["items"] == []
    assert equity["availability"] == "AVAILABLE"
    assert len(equity["items"]) == 1
    assert equity["items"][0]["equity"] == {"amount": "50000.00", "currency": "USD"}
    assert events["availability"] == "AVAILABLE"
    assert len(events["items"]) == 1
    assert events["items"][0]["category"] == "ACCOUNT_INITIALIZED"


def test_paper_broker_fills_flow_into_persistent_account_api(tmp_path) -> None:
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "account.sqlite3")
    _submit_research_paper_fill(runtime, Side.LONG, 6000, T0)

    client = TestClient(create_app(runtime))
    fills = client.get("/api/v1/paper/fills").json()
    positions = client.get("/api/v1/positions").json()
    assert fills["availability"] == "AVAILABLE"
    assert len(fills["items"]) == 1
    assert fills["items"][0]["fill_price"] == "6000.25"
    assert fills["items"][0]["side"] == "LONG"
    assert positions["items"][0]["quantity"] == 1
    assert positions["items"][0]["side"] == "LONG"


def test_completed_round_trip_flows_into_trade_and_equity_apis(tmp_path) -> None:
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "account.sqlite3")
    _submit_research_paper_fill(runtime, Side.LONG, 6000, T0)
    _submit_research_paper_fill(runtime, Side.SHORT, 6002, T0 + timedelta(minutes=2))

    client = TestClient(create_app(runtime))
    trades = client.get("/api/v1/trades").json()
    summary = client.get("/api/v1/dashboard/summary").json()
    equity = client.get("/api/v1/performance/equity?range=all").json()
    assert trades["availability"] == "AVAILABLE"
    assert len(trades["items"]) == 1
    assert trades["items"][0]["symbol"] == "MES"
    assert trades["items"][0]["side"] == "LONG"
    assert trades["items"][0]["net_pnl"] == {"amount": "7.50", "currency": "USD"}
    assert summary["account"]["realized_pnl"] == {"amount": "7.50", "currency": "USD"}
    assert summary["account"]["balance"] == {"amount": "50007.50", "currency": "USD"}
    assert equity["availability"] == "AVAILABLE"
    assert len(equity["items"]) == 5
    assert equity["items"][0]["equity"] == {"amount": "50000.00", "currency": "USD"}
    assert equity["items"][-1]["equity"] == {"amount": "50007.50", "currency": "USD"}


def test_cors_allows_only_local_dashboard_origin(tmp_path) -> None:
    client = _client(tmp_path)
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


def test_api_exposes_no_mutation_routes(tmp_path) -> None:
    schema = _client(tmp_path).get("/openapi.json").json()
    for operations in schema["paths"].values():
        assert set(operations).issubset({"get"})


def test_pagination_rejects_invalid_cursors(tmp_path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/v1/trades?limit=101").status_code == 422
    assert client.get("/api/v1/trades?cursor=-1").status_code == 400
    assert client.get("/api/v1/events?cursor=abc").status_code == 400


def test_pagination_returns_next_cursor_for_paper_fills(tmp_path) -> None:
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "account.sqlite3")
    for index in range(3):
        _submit_research_paper_fill(
            runtime,
            Side.LONG,
            6000 + index,
            T0 + timedelta(minutes=index),
        )
    client = TestClient(create_app(runtime))
    first = client.get("/api/v1/paper/fills?limit=2").json()
    second = client.get(f"/api/v1/paper/fills?limit=2&cursor={first['next_cursor']}").json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] == "2"
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
