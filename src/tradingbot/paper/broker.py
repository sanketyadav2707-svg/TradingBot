"""In-memory paper broker. This module has no network or live-order capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
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
        if (
            not isinstance(commission_per_contract_per_side_usd, (int, float))
            or isinstance(commission_per_contract_per_side_usd, bool)
            or not isfinite(commission_per_contract_per_side_usd)
            or commission_per_contract_per_side_usd < 0
        ):
            raise ValueError("Commission must be finite and non-negative")
        if type(slippage_ticks_per_side) is not int or slippage_ticks_per_side < 0:
            raise ValueError("Slippage ticks must be a non-negative integer")
        self.instrument = instrument
        self.commission = float(commission_per_contract_per_side_usd)
        self.slippage_ticks = slippage_ticks_per_side
        self.fills: list[PaperFill] = []

    def submit_market(
        self, *, side: Side, quantity: int, reference_price: float, timestamp: datetime
    ) -> PaperFill:
        if not isinstance(side, Side) or side not in (Side.LONG, Side.SHORT):
            raise ValueError("A market order side must be Side.LONG or Side.SHORT")
        if type(quantity) is not int or quantity < 1 or quantity > 100:
            raise ValueError("Quantity must be an integer between 1 and 100 contracts")
        if (
            not isinstance(reference_price, (int, float))
            or isinstance(reference_price, bool)
            or not isfinite(reference_price)
        ):
            raise ValueError("Reference price must be finite")
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Paper order timestamp must be timezone-aware")

        # Negative futures prices are valid for some contracts; do not reject them.
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
