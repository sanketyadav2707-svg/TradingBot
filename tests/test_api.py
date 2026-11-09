from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tradingbot.api.app import create_app
from tradingbot.api.runtime import DashboardRuntime
from tradingbot.api.schemas import EquityPointResponse, Money, PositionResponse
from tradingbot.execution.router import AccountRiskSnapshot
from tradingbot.risk.limits import RiskGuard, RiskLimits


def test_health_reports_api_process_without_claiming_trading_session() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]
    assert datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00")).tzinfo


def test_default_summary_does_not_fabricate_account_values() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["environment"] == "DISCONNECTED"
    assert payload["meta"]["source"] == "no-runtime-attached"
    assert payload["account"]["balance"] is None
    assert payload["account"]["equity"] is None
    assert payload["account"]["net_pnl"] is None
    assert payload["market_data"]["connection"] == "DISCONNECTED"


def test_default_risk_snapshot_fails_closed_as_unknown() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/risk/snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gate"] == "UNKNOWN"
    assert "paper_runtime_not_attached" in payload["reasons"]
    assert payload["daily_loss_used"] is None
    assert payload["open_positions"] is None


def test_portfolio_endpoints_return_service_unavailable_when_sources_are_absent() -> None:
    client = TestClient(create_app())

    for path in (
        "/api/v1/positions",
        "/api/v1/trades",
        "/api/v1/performance/equity",
        "/api/v1/events",
    ):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["detail"]["code"]


def test_attached_paper_account_is_reported_with_server_snapshot_and_risk_limits() -> None:
    runtime = DashboardRuntime(
        account_snapshot=AccountRiskSnapshot(
            equity_usd=50_125.50,
            peak_equity_usd=50_200.00,
            daily_pnl_usd=-74.50,
            trades_today=2,
        ),
        risk_guard=RiskGuard(RiskLimits()),
        strategy_name="MNQ ORB15",
        strategy_state="IDLE",
        market_symbols=("MES", "MNQ"),
    )
    client = TestClient(create_app(runtime))

    summary = client.get("/api/v1/dashboard/summary").json()
    risk = client.get("/api/v1/risk/snapshot").json()

    assert summary["meta"]["environment"] == "PAPER"
    assert summary["account"]["equity"] == {"amount": "50125.50", "currency": "USD"}
    assert summary["account"]["max_drawdown"] == {"amount": "74.50", "currency": "USD"}
    assert summary["strategy"]["name"] == "MNQ ORB15"
    assert summary["market_data"]["symbols"] == ["MES", "MNQ"]
    assert risk["gate"] == "UNKNOWN"
    assert "entry_specific_risk_check_not_evaluated" in risk["reasons"]
    assert risk["daily_loss_used"] == {"amount": "74.50", "currency": "USD"}
    assert risk["daily_loss_limit"] == {"amount": "300.00", "currency": "USD"}


def test_daily_loss_gate_is_reported_as_blocked() -> None:
    runtime = DashboardRuntime(
        account_snapshot=AccountRiskSnapshot(
            equity_usd=49_700.00,
            peak_equity_usd=50_000.00,
            daily_pnl_usd=-300.00,
            trades_today=1,
        ),
        risk_guard=RiskGuard(RiskLimits()),
    )
    client = TestClient(create_app(runtime))

    payload = client.get("/api/v1/risk/snapshot").json()

    assert payload["gate"] == "BLOCK"
    assert "maximum_daily_loss_reached" in payload["reasons"]


def test_position_pagination_and_cursor_validation() -> None:
    timestamp = datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)
    positions = tuple(
        PositionResponse(
            id=f"paper-{index}",
            symbol="MES",
            side="LONG",
            quantity=1,
            average_price="6000.00",
            opened_at=timestamp,
        )
        for index in range(3)
    )
    client = TestClient(create_app(DashboardRuntime(positions=positions)))

    first = client.get("/api/v1/positions?limit=2").json()
    second = client.get("/api/v1/positions?limit=2&cursor=2").json()
    invalid = client.get("/api/v1/positions?cursor=-1")

    assert [item["id"] for item in first["items"]] == ["paper-0", "paper-1"]
    assert first["next_cursor"] == "2"
    assert [item["id"] for item in second["items"]] == ["paper-2"]
    assert second["next_cursor"] is None
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "INVALID_CURSOR"



def test_invalid_account_snapshot_is_marked_as_error_and_blocks_risk() -> None:
    runtime = DashboardRuntime(
        account_snapshot=AccountRiskSnapshot(
            equity_usd=float("nan"),
            peak_equity_usd=50_000.00,
            daily_pnl_usd=0.0,
            trades_today=0,
        ),
        risk_guard=RiskGuard(RiskLimits()),
    )
    client = TestClient(create_app(runtime))

    summary = client.get("/api/v1/dashboard/summary").json()
    risk = client.get("/api/v1/risk/snapshot").json()

    assert summary["meta"]["environment"] == "ERROR"
    assert summary["account"]["equity"] is None
    assert risk["gate"] == "BLOCK"
    assert "invalid_account_snapshot" in risk["reasons"]




def test_injected_but_incomplete_runtime_keeps_its_source_name() -> None:
    client = TestClient(create_app(DashboardRuntime(strategy_name="Research only")))

    payload = client.get("/api/v1/dashboard/summary").json()

    assert payload["meta"]["environment"] == "DISCONNECTED"
    assert payload["meta"]["source"] == "injected-paper-runtime"
    assert payload["strategy"]["name"] == "Research only"


def test_equity_history_range_filters_persisted_points() -> None:
    now = datetime.now(timezone.utc)
    points = (
        EquityPointResponse(
            timestamp=now - timedelta(days=2),
            equity=Money(amount="50000.00"),
        ),
        EquityPointResponse(timestamp=now, equity=Money(amount="50025.00")),
    )
    client = TestClient(create_app(DashboardRuntime(equity_points=points)))

    recent = client.get("/api/v1/performance/equity?range=1d").json()
    complete = client.get("/api/v1/performance/equity?range=all").json()

    assert len(recent["items"]) == 1
    assert len(complete["items"]) == 2

def test_api_exposes_only_read_methods() -> None:
    client = TestClient(create_app())

    assert client.post("/health").status_code == 405


def test_dashboard_api_allows_only_configured_local_frontend_origin() -> None:
    client = TestClient(create_app())

    allowed = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = client.options(
        "/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers
