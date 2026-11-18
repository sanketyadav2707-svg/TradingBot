import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from tradingbot.api.app import create_app
from tradingbot.api.runtime import DashboardRuntime, InstrumentConfig
from tradingbot.accounting import PaperAccountStore
from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperFill
from tradingbot.risk.limits import RiskLimits
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
            idempotency_key=f"api-test-{side.name.lower()}-{timestamp.isoformat()}",
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
    assert payload["meta"]["as_of"] == _client(tmp_path).get("/api/v1/performance/equity?range=all").json()["items"][0]["timestamp"]
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
    assert payload["execution_halted"] is False
    assert "risk_gate_has_not_been_evaluated_for_a_running_strategy_session" in payload["reasons"]


def test_risk_api_reports_durable_emergency_halt(tmp_path) -> None:
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "account.sqlite3")
    runtime.account_store.activate_emergency_halt("test_api_halt")
    payload = TestClient(create_app(runtime)).get("/api/v1/risk/snapshot").json()
    assert payload["execution_halted"] is True
    assert payload["gate"] == "UNKNOWN"


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


def test_positions_expose_last_mark_and_timestamp_not_live_quote(tmp_path) -> None:
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "account.sqlite3")
    _submit_research_paper_fill(runtime, Side.LONG, 6000, T0)
    payload = TestClient(create_app(runtime)).get("/api/v1/positions").json()
    assert payload["availability"] == "AVAILABLE"
    position = payload["items"][0]
    assert position["mark_price"] == "6000"
    assert position["mark_timestamp"] == T0.isoformat(timespec="microseconds").replace("+00:00", "Z")
    assert position["unrealized_pnl"] == {"amount": "-1.25", "currency": "USD"}
    assert position["lot_size"] == 1
    assert position["quantity_step"] == 1
    assert position["quantity_freeze"] == 100


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


def test_liveness_is_independent_of_dependency_readiness(tmp_path) -> None:
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "account.sqlite3")
    runtime.account_store = None
    client = TestClient(create_app(runtime))

    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "degraded"
    assert ready.json()["checks"]["paper_account"] == "error"
    assert ready.json()["trading_enabled"] is False
    assert ready.json()["broker_connected"] is False
    assert ready.json()["market_data_connected"] is False


def test_readiness_requires_configuration_instruments_and_paper_database(tmp_path) -> None:
    client = _client(tmp_path)
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"] == {
        "configuration": "ok",
        "risk_configuration": "ok",
        "instruments": "ok",
        "paper_account": "ok",
    }
    assert payload["trading_enabled"] is False
    assert payload["broker_connected"] is False
    assert payload["market_data_connected"] is False
    assert payload["timestamp"].endswith("Z")


def test_nse_session_api_fails_closed_for_closed_and_unverified_dates(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGBOT_NSE_INSTRUMENT_MASTER", raising=False)
    runtime = DashboardRuntime.from_config(database_path=tmp_path / "nse-session.sqlite3")
    client = TestClient(create_app(runtime))

    opened = client.get(
        "/api/v1/markets/nse/session",
        params={"day": "2026-11-16", "segment": "equity"},
    ).json()
    assert opened["status"] == "OPEN"
    assert opened["opens_at"] == "2026-11-16T09:15:00+05:30"
    assert opened["closes_at"] == "2026-11-16T15:30:00+05:30"

    holiday = client.get(
        "/api/v1/markets/nse/session",
        params={"day": "2026-11-24", "segment": "equity"},
    ).json()
    assert holiday["status"] == "CLOSED"

    unknown = client.get(
        "/api/v1/markets/nse/session",
        params={"day": "2027-01-04", "segment": "equity"},
    ).json()
    assert unknown["status"] == "UNKNOWN"
    assert "unverified_nse_calendar_date" in unknown["reason"]


def test_nse_instrument_master_api_reports_unconfigured_and_validated_states(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from tradingbot.api.runtime import DashboardRuntime

    monkeypatch.delenv("TRADINGBOT_NSE_INSTRUMENT_MASTER", raising=False)
    empty_runtime = DashboardRuntime.from_config(
        database_path=tmp_path / "master-empty.sqlite3"
    )
    empty_client = TestClient(create_app(empty_runtime))
    assert empty_client.get("/api/v1/markets/nse/instrument-master").json()["status"] == "NOT_CONFIGURED"

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    master = tmp_path / "nse-master.csv"
    master.write_text(
        "exchange_token,trading_symbol,underlying,segment,instrument_type,expiry,lot_size,quantity_freeze,tick_size,currency_code,source_as_of\n"
        f"12345,NIFTY_TEST_FUT,NIFTY,NSE_FO,FUTIDX,2027-01-28,65,1800,0.05,INR,{today}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TRADINGBOT_NSE_MASTER_VARIANT", "NSE_EXCLUSIVE")
    monkeypatch.setenv("TRADINGBOT_NSE_INSTRUMENT_MASTER", str(master))
    runtime = DashboardRuntime.from_config(
        database_path=tmp_path / "master-valid.sqlite3"
    )
    payload = TestClient(create_app(runtime)).get(
        "/api/v1/markets/nse/instrument-master"
    ).json()
    assert payload["status"] == "VALIDATED"
    assert payload["record_count"] == 1
    assert len(payload["source_file_sha256s"][0]) == 64
    assert payload["source_variant"] == "NSE_EXCLUSIVE"
    assert payload["nse_tradable_count"] == 1
    assert payload["excluded_bse_only_count"] == 0
    assert len(payload["manifest_sha256"]) == 64

    readiness = TestClient(create_app(runtime)).get("/api/v1/markets/nse/readiness").json()
    assert readiness["status"] == "BLOCKED"
    assert readiness["trading_enabled"] is False
    assert readiness["nse_tradable_count"] == 1
    assert "broker_adapter_not_connected" in readiness["reasons"]
    assert "live_market_data_feed_not_connected" in readiness["reasons"]
    assert "verified_broker_fee_schedule_not_configured" in readiness["reasons"]



def test_inr_paper_account_lifecycle_round_trips_through_api(tmp_path) -> None:
    instrument = Instrument(
        "NIFTY_TEST",
        tick_size=0.05,
        tick_value_usd=1.0,
        point_value_usd=20.0,
        currency_code="INR",
    )
    starting_balance = Decimal("100000.00")
    store = PaperAccountStore(
        tmp_path / "inr-account.sqlite3",
        starting_balance_usd=starting_balance,
        currency_code="INR",
    )
    entry_time = datetime(2026, 11, 16, 4, 0, tzinfo=timezone.utc)
    exit_time = entry_time + timedelta(minutes=1)

    store.record_fill(
        PaperFill(
            order_id="inr-entry-001",
            symbol=instrument.symbol,
            side=Side.LONG,
            quantity=1,
            requested_price=25000.0,
            fill_price=25000.0,
            commission_usd=Decimal("1.25"),
            timestamp=entry_time,
            currency_code="INR",
        ),
        instrument,
    )
    store.record_fill(
        PaperFill(
            order_id="inr-exit-001",
            symbol=instrument.symbol,
            side=Side.SHORT,
            quantity=1,
            requested_price=25000.5,
            fill_price=25000.5,
            commission_usd=Decimal("1.25"),
            timestamp=exit_time,
            currency_code="INR",
        ),
        instrument,
    )

    runtime = DashboardRuntime(config_dir=tmp_path)
    runtime.risk_limits = RiskLimits(
        starting_balance_usd=starting_balance,
        max_daily_loss_usd=Decimal("1000"),
        max_total_drawdown_usd=Decimal("5000"),
        max_risk_per_trade_usd=Decimal("100"),
        currency_code="INR",
    )
    runtime.instruments = {
        instrument.symbol: InstrumentConfig(
            instrument=instrument,
            name="NIFTY test contract",
            exchange="NSE",
        )
    }
    runtime.account_store = store
    client = TestClient(create_app(runtime))

    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["account"]["balance"] == {"amount": "100007.50", "currency": "INR"}
    assert summary["account"]["equity"] == {"amount": "100007.50", "currency": "INR"}
    assert summary["account"]["realized_pnl"] == {"amount": "7.50", "currency": "INR"}

    positions = client.get("/api/v1/positions").json()
    assert positions["availability"] == "AVAILABLE"
    assert positions["items"] == []

    trades = client.get("/api/v1/trades").json()
    assert trades["availability"] == "AVAILABLE"
    assert len(trades["items"]) == 1
    assert trades["items"][0]["net_pnl"] == {"amount": "7.50", "currency": "INR"}

    equity = client.get("/api/v1/performance/equity?range=all").json()
    assert equity["availability"] == "AVAILABLE"
    assert equity["items"][-1]["equity"] == {"amount": "100007.50", "currency": "INR"}

    instruments = client.get("/api/v2/instruments").json()
    assert instruments["availability"] == "AVAILABLE"
    nifty = next(item for item in instruments["items"] if item["symbol"] == "NIFTY_TEST")
    assert nifty["currency_code"] == "INR"
    assert nifty["tick_value"] == {"amount": "1.00", "currency": "INR"}
    assert nifty["point_value"] == {"amount": "20.00", "currency": "INR"}



def test_positions_api_includes_explicit_account_currency(tmp_path) -> None:
    runtime = DashboardRuntime.from_config(
        database_path=tmp_path / "positions-currency.sqlite3"
    )
    _submit_research_paper_fill(runtime, Side.LONG, 100.0, T0)
    response = TestClient(create_app(runtime)).get("/api/v1/positions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["availability"] == "AVAILABLE"
    assert payload["items"][0]["currency_code"] == "USD"



def test_dashboard_runtime_prefers_currency_neutral_string_config(tmp_path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "risk.toml").write_text(
        '[risk]\n'
        'currency_code = "INR"\n'
        'starting_balance = "100000.00"\n'
        'daily_loss_limit = "1000.00"\n'
        'total_drawdown_limit = "5000.00"\n'
        'risk_per_trade_limit = "100.00"\n'
        'commission_per_contract_per_side = "0.00"\n'
        'max_contracts = 1\n'
        'max_trades_per_day = 4\n'
        'slippage_ticks_per_side = 1\n'
        'starting_balance_usd = 50000.0\n'
        'max_daily_loss_usd = 300.0\n'
        'max_total_drawdown_usd = 1000.0\n'
        'max_risk_per_trade_usd = 50.0\n',
        encoding="utf-8",
    )
    (config / "instruments.toml").write_text(
        '[instruments.NIFTY_TEST]\n'
        'currency_code = "INR"\n'
        'name = "Nifty Test"\n'
        'exchange = "NSE"\n'
        'tick_size = 0.05\n'
        'tick_value = "1.00"\n'
        'point_value = "20.00"\n',
        encoding="utf-8",
    )
    runtime = DashboardRuntime.from_config(
        config_dir=config,
        database_path=tmp_path / "neutral-config.sqlite3",
    )
    assert runtime.risk_limits is not None
    assert runtime.account_store is not None
    assert runtime.account_store.currency_code == "INR"
    assert runtime.account_store.get_summary()["starting_balance_usd"] == "100000"
    assert runtime.instruments["NIFTY_TEST"].instrument.tick_value.as_dict() == {
        "amount": "1.00",
        "currency": "INR",
    }



def test_nse_instrument_master_api_reports_bse_only_exclusions(tmp_path, monkeypatch):
    from tradingbot.api.runtime import DashboardRuntime

    master = tmp_path / "nse-bse-master-v2.csv"
    master.write_text(
        "exchange_token,trading_symbol,underlying,segment,instrument_type,expiry,lot_size,quantity_freeze,tick_size,currency_code,source_as_of,admission_type\n"
        "12345,NIFTY26DEC_FUT,NIFTY,NSE_FO,FUTIDX,2026-12-29,65,1800,0.05,INR,2026-11-18,1\n"
        "67890,BSEONLY26DEC_FUT,BSEONLY,NSE_FO,FUTSTK,2026-12-29,50,1000,0.05,INR,2026-11-18,2\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "runtime-manifest.json"
    monkeypatch.setenv("TRADINGBOT_NSE_MASTER_VARIANT", "NSE_AND_BSE_EXCLUSIVE")
    monkeypatch.setenv("TRADINGBOT_NSE_INSTRUMENT_MASTER", str(master))
    monkeypatch.setenv("TRADINGBOT_NSE_INSTRUMENT_MASTER_MANIFEST", str(manifest_path))
    runtime = DashboardRuntime.from_config(
        database_path=tmp_path / "nse-bse-api.sqlite3"
    )
    assert manifest_path.exists()
    saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved_manifest["nse_tradable_count"] == 1
    assert saved_manifest["excluded_bse_only_count"] == 1
    payload = TestClient(create_app(runtime)).get(
        "/api/v1/markets/nse/instrument-master"
    ).json()
    assert payload["status"] == "VALIDATED"
    assert payload["source_variant"] == "NSE_AND_BSE_EXCLUSIVE"
    assert payload["record_count"] == 2
    assert payload["nse_tradable_count"] == 1
    assert payload["excluded_bse_only_count"] == 1
    assert len(payload["manifest_sha256"]) == 64
