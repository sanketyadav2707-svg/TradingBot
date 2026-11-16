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

class ReadinessResponse(StrictResponse):
    status: Literal["ready", "degraded"]
    timestamp: str
    checks: dict[str, Literal["ok", "error"]]
    reasons: list[str]
    trading_enabled: Literal[False] = False
    broker_connected: Literal[False] = False
    market_data_connected: Literal[False] = False


class Money(StrictResponse):
    amount: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")


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
    execution_halted: bool | None


class InstrumentMetadataV2(StrictResponse):
    """Currency-neutral instrument fields; legacy v1 names remain unchanged."""
    symbol: str
    name: str
    exchange: str
    tick_size: str
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    tick_value: Money
    point_value: Money


class InstrumentsV2Response(StrictResponse):
    availability: AvailabilityState
    source: str
    items: list[InstrumentMetadataV2]
    reason: str | None = None


class NSESessionResponse(StrictResponse):
    status: Literal["OPEN", "CLOSED", "UNKNOWN", "NOT_CONFIGURED"]
    day: str
    segment: str
    timezone: str = "Asia/Kolkata"
    session_name: str | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    reason: str | None = None


class NSEInstrumentMasterResponse(StrictResponse):
    status: Literal["VALIDATED", "INVALID", "NOT_CONFIGURED"]
    record_count: int
    latest_source_as_of: str | None = None
    source_file_sha256s: list[str] = Field(default_factory=list)
    source_variant: str | None = None
    nse_tradable_count: int = 0
    excluded_bse_only_count: int = 0
    manifest_sha256: str | None = None
    reason: str | None = None


class NSEMarketReadinessResponse(StrictResponse):
    status: Literal["BLOCKED"]
    reasons: list[str]
    calendar_coverage_start: str | None = None
    calendar_coverage_end: str | None = None
    master_status: Literal["VALIDATED", "INVALID", "NOT_CONFIGURED"]
    source_variant: str
    record_count: int
    nse_tradable_count: int
    excluded_bse_only_count: int
    manifest_sha256: str | None = None
    broker_connected: Literal[False] = False
    market_data_connected: Literal[False] = False
    broker_fee_schedule_configured: Literal[False] = False
    trading_enabled: Literal[False] = False
