"""Composition layer for persistent local paper-account execution.

This factory only creates explicit in-process PaperBroker instances. It never
starts a strategy, market-data feed, scheduler, or background trading loop.
"""

from __future__ import annotations

import threading

from tradingbot.accounting.sqlite_store import PaperAccountStore
from tradingbot.models import Instrument
from tradingbot.paper.broker import PaperBroker


class PaperAccountEngine:
    """Create paper brokers whose fills are persisted before being acknowledged."""

    def __init__(
        self,
        store: PaperAccountStore,
        *,
        commission_per_contract_per_side_usd: float = 0.0,
        slippage_ticks_per_side: int = 1,
    ) -> None:
        self.store = store
        self.commission = commission_per_contract_per_side_usd
        self.slippage_ticks = slippage_ticks_per_side
        self._brokers: dict[str, PaperBroker] = {}
        self._lock = threading.RLock()

    def broker_for(self, instrument: Instrument) -> PaperBroker:
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        symbol = instrument.symbol.strip().upper()
        with self._lock:
            existing = self._brokers.get(symbol)
            if existing is not None:
                if existing.instrument != instrument:
                    raise ValueError(
                        "Instrument specification changed for an existing broker; "
                        "restart only after reconciling open paper positions"
                    )
                return existing

            broker = PaperBroker(
                instrument,
                commission_per_contract_per_side_usd=self.commission,
                slippage_ticks_per_side=self.slippage_ticks,
                on_fill=lambda fill: self.store.record_fill(fill, instrument),
            )
            self._brokers[symbol] = broker
            return broker

    @property
    def active_symbols(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._brokers))
