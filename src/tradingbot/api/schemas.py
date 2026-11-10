"""Pydantic response schemas for the read-only dashboard API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EnvironmentState = Literal["DEMO", "PAPER", "DISCONNECTED", "STALE", "ERROR"]
AvailabilityState = Literal["AVAILABLE", "NOT_CONFIGURED", "NOT_PERSISTED", "NOT_IMPLEMENTED"]


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictResponse):
    status: Literal["ok", "degraded", "error"]
    version: str
    timestamp: str


class Money(StrictResponse):
    amount: str
    currency: Literal["USD"] = "USD"


class ApiMeta(StrictResponse):
    as_of: str
    environment: EnvironmentState
    source: str


class DashboardSummaryResponse(StrictResponse):
    meta: ApiMeta
    account: dict[str, Money | None]
    strategy: dict[str, str | None]
    market_data: dict[str, str | list[str] | None]


class AvailabilityPage(StrictResponse):
    availability: AvailabilityState
    items: list[dict]
    next_cursor: str | None = None
    reason: str | None = None


class InstrumentMetadata(StrictResponse):
    symbol: str
    name: str
    exchange: str
    tick_size: str
    tick_value_usd: Money
    point_value_usd: Money


class InstrumentsResponse(StrictResponse):
    availability: AvailabilityState
    source: str
    items: list[InstrumentMetadata]
    reason: str | None = None


class PaperFill(StrictResponse):
    order_id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: int = Field(ge=1)
    requested_price: str
    fill_price: str
    commission: Money
    timestamp: str


class PaperFillsResponse(StrictResponse):
    availability: AvailabilityState
    items: list[PaperFill]
    next_cursor: str | None = None
    reason: str | None = None


class RiskSnapshotResponse(StrictResponse):
    meta: ApiMeta
    gate: Literal["PASS", "BLOCK", "UNKNOWN"]
    reasons: list[str]
    daily_loss_used: Money | None
    daily_loss_limit: Money | None
    open_positions: int | None
    max_contracts: int | None
