"""FastAPI application exposing read-only TradingBot dashboard endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import isfinite
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from tradingbot import __version__
from tradingbot.api.runtime import DashboardRuntime
from tradingbot.api.schemas import (
    AccountSummary,
    ApiMeta,
    DashboardSummaryResponse,
    EquityHistoryResponse,
    HealthResponse,
    MarketDataSummary,
    Money,
    OperationalEventResponse,
    PageResponse,
    PositionResponse,
    RiskSnapshotResponse,
    StrategySummary,
    TradeResponse,
)


T = TypeVar("T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: float | int) -> Money:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    return Money(amount=format(amount, "f"))


def _snapshot_is_valid(snapshot: object) -> bool:
    if snapshot is None:
        return False
    try:
        equity = snapshot.equity_usd  # type: ignore[attr-defined]
        peak = snapshot.peak_equity_usd  # type: ignore[attr-defined]
        daily_pnl = snapshot.daily_pnl_usd  # type: ignore[attr-defined]
        trades_today = snapshot.trades_today  # type: ignore[attr-defined]
    except AttributeError:
        return False
    numbers = (equity, peak, daily_pnl)
    return (
        all(isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) for value in numbers)
        and peak >= equity
        and type(trades_today) is int
        and trades_today >= 0
    )


def _meta(runtime: DashboardRuntime, environment: str, *, runtime_attached: bool) -> ApiMeta:
    source = runtime.source_name if runtime_attached else "no-runtime-attached"
    return ApiMeta(as_of=_utc_now(), environment=environment, source=source)  # type: ignore[arg-type]


def _unavailable(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=503, detail={"code": code, "message": message})


def _page(items: tuple[T, ...], *, limit: int, cursor: str | None) -> tuple[list[T], str | None]:
    try:
        offset = int(cursor) if cursor is not None else 0
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CURSOR", "message": "Cursor must be a non-negative integer."},
        ) from exc
    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CURSOR", "message": "Cursor must be a non-negative integer."},
        )
    page = list(items[offset : offset + limit])
    next_offset = offset + len(page)
    next_cursor = str(next_offset) if next_offset < len(items) else None
    return page, next_cursor


def create_app(runtime: DashboardRuntime | None = None) -> FastAPI:
    """Create the API application; by default no trading runtime is attached."""

    app = FastAPI(
        title="TradingBot Read-only Dashboard API",
        version=__version__,
        description=(
            "Local, read-only observability API. It does not place orders, "
            "change risk limits, start strategies, or connect live brokers."
        ),
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.dashboard_runtime = runtime if runtime is not None else DashboardRuntime()
    app.state.dashboard_runtime_attached = runtime is not None

    configured_origins = os.getenv(
        "TRADINGBOT_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
        max_age=600,
    )

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, timestamp=_utc_now())

    @app.get("/api/v1/dashboard/summary", response_model=DashboardSummaryResponse, tags=["dashboard"])
    def dashboard_summary(request: Request) -> DashboardSummaryResponse:
        current: DashboardRuntime = request.app.state.dashboard_runtime
        account = current.account_snapshot
        risk_guard = current.risk_guard
        valid_account = _snapshot_is_valid(account)
        environment = (
            "ERROR" if account is not None and not valid_account
            else "PAPER" if valid_account and risk_guard is not None
            else "DISCONNECTED"
        )

        account_summary = AccountSummary()
        if valid_account and account is not None:
            account_summary.equity = _money(account.equity_usd)
            account_summary.max_drawdown = _money(
                max(0.0, account.peak_equity_usd - account.equity_usd)
            )

        strategy_state = current.strategy_state
        if strategy_state not in {"IDLE", "RUNNING", "HALTED", "ERROR", "UNKNOWN"}:
            strategy_state = "UNKNOWN"

        market_update = current.market_data_last_update
        return DashboardSummaryResponse(
            meta=_meta(current, environment, runtime_attached=request.app.state.dashboard_runtime_attached),
            account=account_summary,
            strategy=StrategySummary(name=current.strategy_name, state=strategy_state),
            market_data=MarketDataSummary(
                connection="CONNECTED" if current.market_data_connected else "DISCONNECTED",
                last_update=market_update,
                symbols=list(current.market_symbols),
            ),
        )

    @app.get("/api/v1/risk/snapshot", response_model=RiskSnapshotResponse, tags=["risk"])
    def risk_snapshot(request: Request) -> RiskSnapshotResponse:
        current: DashboardRuntime = request.app.state.dashboard_runtime
        account = current.account_snapshot
        guard = current.risk_guard
        valid_account = _snapshot_is_valid(account)
        environment = (
            "ERROR" if account is not None and not valid_account
            else "PAPER" if valid_account and guard is not None
            else "DISCONNECTED"
        )

        reasons: list[str] = []
        daily_loss_used = None
        daily_loss_limit = None
        gate = "UNKNOWN"
        if account is not None and not valid_account:
            gate = "BLOCK"
            reasons.append("invalid_account_snapshot")
        else:
            if not request.app.state.dashboard_runtime_attached:
                reasons.append("paper_runtime_not_attached")
            if account is None:
                reasons.append("account_snapshot_unavailable")
            else:
                daily_loss_used = _money(max(0.0, -account.daily_pnl_usd))

            if guard is None:
                reasons.append("risk_guard_not_attached")
            else:
                daily_loss_limit = _money(guard.limits.max_daily_loss_usd)

            if account is not None and guard is not None:
                limits = guard.limits
                if account.equity_usd <= 0:
                    gate = "BLOCK"
                    reasons.append("non_positive_equity")
                if account.peak_equity_usd - account.equity_usd >= limits.max_total_drawdown_usd:
                    gate = "BLOCK"
                    reasons.append("maximum_total_drawdown_reached")
                if account.daily_pnl_usd <= -limits.max_daily_loss_usd:
                    gate = "BLOCK"
                    reasons.append("maximum_daily_loss_reached")
                if account.trades_today >= limits.max_trades_per_day:
                    gate = "BLOCK"
                    reasons.append("max_trades_per_day_reached")
                if gate != "BLOCK":
                    reasons.append("entry_specific_risk_check_not_evaluated")

        return RiskSnapshotResponse(
            meta=_meta(current, environment, runtime_attached=request.app.state.dashboard_runtime_attached),
            gate=gate,  # type: ignore[arg-type]
            reasons=reasons,
            daily_loss_used=daily_loss_used,
            daily_loss_limit=daily_loss_limit,
            open_positions=None,
            max_positions=None,
        )

    @app.get("/api/v1/positions", response_model=PageResponse[PositionResponse], tags=["portfolio"])
    def positions(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = None,
    ) -> PageResponse[PositionResponse]:
        current: DashboardRuntime = request.app.state.dashboard_runtime
        if current.positions is None:
            raise _unavailable(
                "POSITION_SOURCE_UNAVAILABLE",
                "No portfolio/position ledger is attached to the API runtime.",
            )
        items, next_cursor = _page(current.positions, limit=limit, cursor=cursor)
        return PageResponse[PositionResponse](items=items, next_cursor=next_cursor)

    @app.get("/api/v1/trades", response_model=PageResponse[TradeResponse], tags=["portfolio"])
    def trades(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = None,
    ) -> PageResponse[TradeResponse]:
        current: DashboardRuntime = request.app.state.dashboard_runtime
        if current.trades is None:
            raise _unavailable(
                "TRADE_LEDGER_UNAVAILABLE",
                "No persisted paper trade ledger is attached to the API runtime.",
            )
        items, next_cursor = _page(current.trades, limit=limit, cursor=cursor)
        return PageResponse[TradeResponse](items=items, next_cursor=next_cursor)

    @app.get("/api/v1/performance/equity", response_model=EquityHistoryResponse, tags=["performance"])
    def equity_history(
        request: Request,
        range: str = Query(default="1d", pattern="^(1d|1w|1m|all)$"),
    ) -> EquityHistoryResponse:
        current: DashboardRuntime = request.app.state.dashboard_runtime
        if current.equity_points is None:
            raise _unavailable(
                "EQUITY_HISTORY_UNAVAILABLE",
                "No persisted equity history is attached to the API runtime.",
            )
        days_by_range = {"1d": 1, "1w": 7, "1m": 30}
        points = list(current.equity_points)
        if range != "all":
            cutoff = _utc_now() - timedelta(days=days_by_range[range])
            points = [point for point in points if point.timestamp >= cutoff]
        return EquityHistoryResponse(items=points)

    @app.get("/api/v1/events", response_model=PageResponse[OperationalEventResponse], tags=["operations"])
    def events(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = None,
    ) -> PageResponse[OperationalEventResponse]:
        current: DashboardRuntime = request.app.state.dashboard_runtime
        if current.events is None:
            raise _unavailable(
                "EVENT_STORE_UNAVAILABLE",
                "No append-only event store is attached to the API runtime.",
            )
        items, next_cursor = _page(current.events, limit=limit, cursor=cursor)
        return PageResponse[OperationalEventResponse](items=items, next_cursor=next_cursor)

    return app


app = create_app()
