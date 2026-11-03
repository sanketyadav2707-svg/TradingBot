"""In-memory paper broker. This module has no network or live-order capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from tradingbot.models import Instrument, Side


@dataclass(frozen=True, slots=True)
class PaperFill:
    order_id: str
    symbol: str
    side: Side
    quantity: int
    requested_price: float
    fill_price: float
    commission_usd: float
    timestamp: datetime


class PaperBroker:
    """A deliberately small simulated market-order adapter for local experiments."""

    def __init__(
        self,
        instrument: Instrument,
        commission_per_contract_per_side_usd: float = 0.0,
        slippage_ticks_per_side: int = 1,
    ) -> None:
        if commission_per_contract_per_side_usd < 0 or slippage_ticks_per_side < 0:
            raise ValueError("Commission and slippage cannot be negative")
        self.instrument = instrument
        self.commission = commission_per_contract_per_side_usd
        self.slippage_ticks = slippage_ticks_per_side
        self.fills: list[PaperFill] = []

    def submit_market(
        self, *, side: Side, quantity: int, reference_price: float, timestamp: datetime
    ) -> PaperFill:
        if side == Side.FLAT:
            raise ValueError("A market order must be LONG or SHORT")
        if quantity < 1 or reference_price <= 0:
            raise ValueError("Quantity and reference price must be positive")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Paper order timestamp must be timezone-aware")
        if quantity > 100:
            raise ValueError("Paper broker safety cap is 100 contracts")
        fill = reference_price + int(side) * self.slippage_ticks * self.instrument.tick_size
        record = PaperFill(
            order_id=str(uuid4()),
            symbol=self.instrument.symbol,
            side=side,
            quantity=quantity,
            requested_price=reference_price,
            fill_price=fill,
            commission_usd=self.commission * quantity,
            timestamp=timestamp,
        )
        self.fills.append(record)
        return record
