"""Loopback-only, read-only FastAPI surface for the TradingBot dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
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
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _money(value: float | int | Decimal | None) -> Money | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Money values must be valid finite decimals") from exc
    if not amount.is_finite():
        raise ValueError("Money values must be finite")
    return Money(amount=format(amount.quantize(Decimal("0.01")), "f"), currency="USD")


def _page_slice(items: list[Any], limit: int, cursor: str | None) -> tuple[list[Any], str | None]:
    if cursor is None:
        offset = 0
    else:
        try:
            offset = int(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="cursor_must_be_a_non_negative_integer") from exc
        if offset < 0:
            raise HTTPException(status_code=400, detail="cursor_must_be_a_non_negative_integer")
    page = items[offset : offset + limit]
    next_offset = offset + len(page)
    next_cursor = str(next_offset) if next_offset < len(items) else None
    return page, next_cursor


def create_app(runtime: DashboardRuntime | None = None) -> FastAPI:
    """Create the dashboard API. No broker or trading process is started here."""
    dashboard_runtime = runtime or DashboardRuntime.from_config()
    app = FastAPI(
        title="TradingBot Read-only Dashboard API",
        version="1.0.0",
        description=(
            "Local read-only status and configuration API. No order placement, " 
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

    def meta(source: str) -> ApiMeta:
        environment = "PAPER" if dashboard_runtime.paper_broker is not None else "DISCONNECTED"
        return ApiMeta(as_of=_utc_now(), environment=environment, source=source)

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

    @app.get("/api/v1/dashboard/summary", response_model=DashboardSummaryResponse, tags=["dashboard"])
    def dashboard_summary() -> DashboardSummaryResponse:
        source = "local-config-and-runtime" if dashboard_runtime.paper_broker else "local-config-only"
        return DashboardSummaryResponse(
            meta=meta(source),
            account={
                "balance": None,
                "equity": None,
                "realized_pnl": None,
                "unrealized_pnl": None,
                "net_pnl": None,
                "max_drawdown": None,
            },
            strategy={"name": None, "state": "UNKNOWN"},
            market_data={
                "connection": "DISCONNECTED",
                "last_update": None,
                "symbols": [],
            },
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

    @app.get("/api/v1/positions", response_model=AvailabilityPage, tags=["paper state"])
    def positions() -> AvailabilityPage:
        return AvailabilityPage(
            availability="NOT_IMPLEMENTED",
            items=[],
            reason="no_position_book_is_implemented; raw broker fills are not open positions",
        )

    @app.get("/api/v1/trades", response_model=AvailabilityPage, tags=["paper state"])
    def trades(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> AvailabilityPage:
        page, next_cursor = _page_slice([], limit, cursor)
        return AvailabilityPage(
            availability="NOT_PERSISTED",
            items=page,
            next_cursor=next_cursor,
            reason="no_closed_trade_ledger_is_persisted; broker fills are not completed trades",
        )

    @app.get("/api/v1/paper/fills", response_model=PaperFillsResponse, tags=["paper state"])
    def paper_fills(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> PaperFillsResponse:
        broker = dashboard_runtime.paper_broker
        if broker is None:
            return PaperFillsResponse(
                availability="NOT_CONFIGURED",
                items=[],
                reason="no_paper_broker_instance_has_been_attached_to_the_dashboard_runtime",
            )
        snapshot = list(broker.fills)
        selected, next_cursor = _page_slice(snapshot, limit, cursor)
        items = [
            PaperFill(
                order_id=fill.order_id,
                symbol=fill.symbol,
                side="LONG" if int(fill.side) > 0 else "SHORT",
                quantity=fill.quantity,
                requested_price=format(Decimal(str(fill.requested_price)), "f"),
                fill_price=format(Decimal(str(fill.fill_price)), "f"),
                commission=_money(fill.commission_usd),
                timestamp=fill.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            for fill in selected
        ]
        return PaperFillsResponse(availability="AVAILABLE", items=items, next_cursor=next_cursor)

    @app.get("/api/v1/performance/equity", tags=["performance"])
    def equity(range: str = Query(default="1d", pattern="^(1d|1w|1m|all)$")) -> dict[str, Any]:
        return {
            "availability": "NOT_PERSISTED",
            "items": [],
            "reason": "no_authoritative_equity_history_is_persisted",
            "range": range,
        }

    @app.get("/api/v1/risk/snapshot", response_model=RiskSnapshotResponse, tags=["risk"])
    def risk_snapshot() -> RiskSnapshotResponse:
        limits = dashboard_runtime.risk_limits
        reasons = [
            "account_snapshot_unavailable",
            "position_state_unavailable",
            "risk_gate_has_not_been_evaluated_for_a_running_session",
        ]
        if limits is None:
            reasons.append("risk_configuration_unavailable_or_invalid")
        return RiskSnapshotResponse(
            meta=meta("config/risk.toml" if limits else "risk-config-unavailable"),
            gate="UNKNOWN",
            reasons=reasons,
            daily_loss_used=None,
            daily_loss_limit=_money(limits.max_daily_loss_usd) if limits else None,
            open_positions=None,
            max_contracts=limits.max_contracts if limits else None,
        )

    @app.get("/api/v1/events", response_model=AvailabilityPage, tags=["operations"])
    def events(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> AvailabilityPage:
        page, next_cursor = _page_slice([], limit, cursor)
        return AvailabilityPage(
            availability="NOT_IMPLEMENTED",
            items=page,
            next_cursor=next_cursor,
            reason="append_only_operational_event_store_is_not_implemented",
        )

    return app


app = create_app()
