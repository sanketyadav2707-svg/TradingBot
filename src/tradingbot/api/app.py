"""Loopback-only, read-only FastAPI surface for the persistent paper account."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from tradingbot.api.runtime import DashboardRuntime
from tradingbot.api.schemas import (
    ApiMeta,
    AvailabilityPage,
    DashboardSummaryResponse,
    HealthResponse,
    InstrumentMetadata,
    InstrumentsResponse,
    Money,
    PaperFill,
    PaperFillsResponse,
    RiskSnapshotResponse,
    ReadinessResponse,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _money(value: str | float | int | Decimal | None) -> Money | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Money values must be valid finite decimals") from exc
    if not amount.is_finite():
        raise ValueError("Money values must be finite")
    return Money(amount=format(amount.quantize(Decimal("0.01")), "f"), currency="USD")


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="cursor_must_be_a_non_negative_integer") from exc
    if offset < 0:
        raise HTTPException(status_code=400, detail="cursor_must_be_a_non_negative_integer")
    return offset


def _next_cursor(offset: int, returned: int, total: int) -> str | None:
    next_offset = offset + returned
    return str(next_offset) if next_offset < total else None


def create_app(runtime: DashboardRuntime | None = None) -> FastAPI:
    """Create the dashboard API. No broker, strategy or market-data process is started."""
    dashboard_runtime = runtime or DashboardRuntime.from_config()
    app = FastAPI(
        title="TradingBot Read-only Dashboard API",
        version="1.1.0",
        description=(
            "Local read-only paper-account and configuration API. No order placement, "
            "risk mutation, broker connection, or live execution routes are exposed."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.dashboard_runtime = dashboard_runtime
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )

    def meta(source: str, as_of: str | None = None) -> ApiMeta:
        environment = "PAPER" if dashboard_runtime.account_store is not None else "DISCONNECTED"
        return ApiMeta(as_of=as_of or _utc_now(), environment=environment, source=source)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        try:
            package_version = version("personal-futures-tradingbot")
        except PackageNotFoundError:
            package_version = "0.1.0"
        return HealthResponse(
            status="degraded" if dashboard_runtime.configuration_errors else "ok",
            version=package_version,
            timestamp=_utc_now(),
        )

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def liveness() -> HealthResponse:
        """Report only that the API process can answer requests."""
        try:
            package_version = version("personal-futures-tradingbot")
        except PackageNotFoundError:
            package_version = "0.1.0"
        return HealthResponse(status="ok", version=package_version, timestamp=_utc_now())

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    def readiness() -> ReadinessResponse:
        """Check dashboard dependencies without implying trading readiness."""
        checks: dict[str, str] = {
            "configuration": "error" if dashboard_runtime.configuration_errors else "ok",
            "risk_configuration": "ok" if dashboard_runtime.risk_limits is not None else "error",
            "instruments": "ok" if dashboard_runtime.instruments else "error",
            "paper_account": "error",
        }
        store = dashboard_runtime.account_store
        if store is not None:
            try:
                # A real read detects missing, corrupt, or inaccessible SQLite state.
                store.get_summary()
                checks["paper_account"] = "ok"
            except Exception:
                checks["paper_account"] = "error"

        reasons = [f"{name}_unavailable_or_invalid" for name, status in checks.items() if status != "ok"]
        return ReadinessResponse(
            status="ready" if not reasons else "degraded",
            timestamp=_utc_now(),
            checks=checks,
            reasons=reasons,
            trading_enabled=False,
            broker_connected=False,
            market_data_connected=False,
        )

    @app.get("/api/v1/dashboard/summary", response_model=DashboardSummaryResponse, tags=["dashboard"])
    def dashboard_summary() -> DashboardSummaryResponse:
        store = dashboard_runtime.account_store
        snapshot = store.get_summary() if store is not None else None
        source = "sqlite-paper-account" if snapshot is not None else "local-config-only"
        account = {
            "balance": _money(snapshot["balance_usd"]) if snapshot else None,
            "equity": _money(snapshot["equity_usd"]) if snapshot else None,
            "realized_pnl": _money(snapshot["realized_net_pnl_usd"]) if snapshot else None,
            "unrealized_pnl": _money(snapshot["unrealized_pnl_usd"]) if snapshot else None,
            "net_pnl": _money(snapshot["net_pnl_usd"]) if snapshot else None,
            "max_drawdown": _money(snapshot["max_drawdown_usd"]) if snapshot else None,
        }
        return DashboardSummaryResponse(
            meta=meta(source, snapshot["as_of"] if snapshot else None),
            account=account,
            strategy={"name": None, "state": "UNKNOWN"},
            market_data={"connection": "DISCONNECTED", "last_update": None, "symbols": []},
        )

    @app.get("/api/v1/instruments", response_model=InstrumentsResponse, tags=["market metadata"])
    def instruments() -> InstrumentsResponse:
        items = [
            InstrumentMetadata(
                symbol=symbol,
                name=record.name,
                exchange=record.exchange,
                tick_size=format(Decimal(str(record.instrument.tick_size)), "f"),
                tick_value_usd=_money(record.instrument.tick_value_usd),
                point_value_usd=_money(record.instrument.point_value_usd),
            )
            for symbol, record in sorted(dashboard_runtime.instruments.items())
        ]
        availability = "AVAILABLE" if items else "NOT_CONFIGURED"
        return InstrumentsResponse(
            availability=availability,
            source="config/instruments.toml",
            items=items,
            reason=None if items else "instrument_configuration_unavailable_or_invalid",
        )

    @app.get("/api/v1/positions", response_model=AvailabilityPage, tags=["paper account"])
    def positions() -> AvailabilityPage:
        store = dashboard_runtime.account_store
        if store is None:
            return AvailabilityPage(
                availability="NOT_CONFIGURED", items=[], reason="persistent_paper_account_unavailable"
            )
        items = [
            {
                "id": item["symbol"],
                "symbol": item["symbol"],
                "side": item["side"],
                "quantity": item["quantity"],
                "average_price": item["average_entry_price"],
                "unrealized_pnl": _money(item["unrealized_pnl_usd"]),
                "mark_price": item["mark_price"],
                "mark_timestamp": item["mark_timestamp"],
                "opened_at": item["opened_at"],
            }
            for item in store.list_positions()
        ]
        return AvailabilityPage(availability="AVAILABLE", items=items)

    @app.get("/api/v1/trades", response_model=AvailabilityPage, tags=["paper account"])
    def trades(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> AvailabilityPage:
        store = dashboard_runtime.account_store
        if store is None:
            return AvailabilityPage(
                availability="NOT_CONFIGURED", items=[], reason="persistent_paper_account_unavailable"
            )
        offset = _cursor_offset(cursor)
        total = store.count_records("closed_trades")
        rows = store.list_trades(limit=limit, offset=offset)
        items = [
            {
                "id": str(row["id"]),
                "symbol": row["symbol"],
                "side": row["side"],
                "quantity": row["quantity"],
                "entry_time": row["entry_time"],
                "exit_time": row["exit_time"],
                "entry_price": row["entry_price"],
                "exit_price": row["exit_price"],
                "net_pnl": _money(row["net_pnl_usd"]),
                "exit_reason": "OPPOSING_FILL_FIFO",
            }
            for row in rows
        ]
        return AvailabilityPage(
            availability="AVAILABLE",
            items=items,
            next_cursor=_next_cursor(offset, len(items), total),
        )

    @app.get("/api/v1/paper/fills", response_model=PaperFillsResponse, tags=["paper account"])
    def paper_fills(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> PaperFillsResponse:
        store = dashboard_runtime.account_store
        if store is None:
            return PaperFillsResponse(
                availability="NOT_CONFIGURED",
                items=[],
                reason="persistent_paper_account_unavailable",
            )
        offset = _cursor_offset(cursor)
        total = store.count_records("fills")
        rows = store.list_fills(limit=limit, offset=offset)
        items = [
            PaperFill(
                order_id=row["order_id"],
                symbol=row["symbol"],
                side=row["side"],
                quantity=row["quantity"],
                requested_price=row["requested_price"],
                fill_price=row["fill_price"],
                commission=_money(row["commission_usd"]),
                timestamp=row["timestamp"],
            )
            for row in rows
        ]
        return PaperFillsResponse(
            availability="AVAILABLE",
            items=items,
            next_cursor=_next_cursor(offset, len(items), total),
        )

    @app.get("/api/v1/performance/equity", tags=["performance"])
    def equity(range: str = Query(default="1d", pattern="^(1d|1w|1m|all)$")) -> dict[str, Any]:
        store = dashboard_runtime.account_store
        if store is None:
            return {
                "availability": "NOT_CONFIGURED",
                "items": [],
                "reason": "persistent_paper_account_unavailable",
                "range": range,
            }
        now = datetime.now(timezone.utc)
        durations = {
            "1d": timedelta(days=1),
            "1w": timedelta(days=7),
            "1m": timedelta(days=30),
            "all": None,
        }
        lower_bound = now - durations[range] if durations[range] is not None else None
        rows = store.list_equity(limit=5000)
        selected = []
        for row in rows:
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if lower_bound is None or stamp >= lower_bound:
                selected.append({
                    "timestamp": row["timestamp"],
                    "equity": _money(row["equity_usd"]),
                })
        return {
            "availability": "AVAILABLE" if selected else "NOT_PERSISTED",
            "items": selected,
            "reason": None if selected else "no_equity_observations_in_requested_range",
            "range": range,
        }

    @app.get("/api/v1/risk/snapshot", response_model=RiskSnapshotResponse, tags=["risk"])
    def risk_snapshot() -> RiskSnapshotResponse:
        limits = dashboard_runtime.risk_limits
        store = dashboard_runtime.account_store
        account_snapshot = store.get_summary() if store is not None else None
        reasons = [
            "risk_gate_has_not_been_evaluated_for_a_running_strategy_session",
            "risk_configuration_is_illustrative_research_default_not_verified_firm_rule_profile",
        ]
        if account_snapshot is None:
            reasons.append("paper_account_snapshot_unavailable")
        return RiskSnapshotResponse(
            meta=meta("config-and-paper-account" if account_snapshot else "risk-config-unavailable"),
            gate="UNKNOWN",
            reasons=reasons,
            daily_loss_used=None,
            daily_loss_limit=_money(limits.max_daily_loss_usd) if limits else None,
            open_positions=account_snapshot["open_positions"] if account_snapshot else None,
            max_contracts=limits.max_contracts if limits else None,
            execution_halted=store.emergency_halt_active if store is not None else None,
        )

    @app.get("/api/v1/events", response_model=AvailabilityPage, tags=["operations"])
    def events(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> AvailabilityPage:
        store = dashboard_runtime.account_store
        if store is None:
            return AvailabilityPage(
                availability="NOT_CONFIGURED", items=[], reason="persistent_paper_account_unavailable"
            )
        offset = _cursor_offset(cursor)
        total = store.count_records("account_events")
        rows = store.list_events(limit=limit, offset=offset)
        items = [
            {
                "id": str(row["id"]),
                "timestamp": row["timestamp"],
                "severity": "INFO" if row["event_type"] not in {"TRADE_CLOSED"} else "INFO",
                "category": row["event_type"],
                "message": str(row["payload"]),
            }
            for row in rows
        ]
        return AvailabilityPage(
            availability="AVAILABLE",
            items=items,
            next_cursor=_next_cursor(offset, len(items), total),
        )

    return app


app = create_app()
