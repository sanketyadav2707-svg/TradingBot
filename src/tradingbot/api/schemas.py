"""Pydantic response schemas for the read-only dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EnvironmentState = Literal["DEMO", "PAPER", "DISCONNECTED", "STALE", "ERROR"]
ConnectionState = Literal["CONNECTED", "DISCONNECTED", "DELAYED", "UNKNOWN"]


class ApiMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: datetime = Field(description="UTC timestamp when this snapshot was assembled.")
    environment: EnvironmentState
    source: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    timestamp: datetime


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: str = Field(pattern=r"^-?[0-9]+(\.[0-9]+)?$")
    currency: Literal["USD"] = "USD"


class AccountSummary(BaseModel):
    balance: Money | None = None
    equity: Money | None = None
    realized_pnl: Money | None = None
    unrealized_pnl: Money | None = None
    net_pnl: Money | None = None
    max_drawdown: Money | None = None


class StrategySummary(BaseModel):
    name: str | None = None
    state: Literal["IDLE", "RUNNING", "HALTED", "ERROR", "UNKNOWN"] = "UNKNOWN"


class MarketDataSummary(BaseModel):
    connection: ConnectionState = "UNKNOWN"
    last_update: datetime | None = None
    symbols: list[str] = Field(default_factory=list)


class DashboardSummaryResponse(BaseModel):
    meta: ApiMeta
    account: AccountSummary
    strategy: StrategySummary
    market_data: MarketDataSummary


class PositionResponse(BaseModel):
    id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: int = Field(ge=1)
    average_price: str
    unrealized_pnl: Money | None = None
    opened_at: datetime


class TradeResponse(BaseModel):
    id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: int = Field(ge=1)
    entry_time: datetime
    exit_time: datetime
    entry_price: str
    exit_price: str
    net_pnl: Money
    exit_reason: str


class PageResponse[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class EquityPointResponse(BaseModel):
    timestamp: datetime
    equity: Money


class EquityHistoryResponse(BaseModel):
    items: list[EquityPointResponse]


class RiskSnapshotResponse(BaseModel):
    meta: ApiMeta
    gate: Literal["PASS", "BLOCK", "UNKNOWN"]
    reasons: list[str] = Field(default_factory=list)
    daily_loss_used: Money | None = None
    daily_loss_limit: Money | None = None
    open_positions: int | None = Field(default=None, ge=0)
    max_positions: int | None = Field(default=None, ge=0)


class OperationalEventResponse(BaseModel):
    id: str
    timestamp: datetime
    severity: Literal["INFO", "WARNING", "ERROR"]
    category: str
    message: str
