"""Risk-gated composition layer for persistent local paper execution.

This module only creates paper brokers behind ExecutionRouter. It never starts
a strategy, market-data feed, scheduler, or background trading loop.
"""

from __future__ import annotations

import threading

from tradingbot.accounting.sqlite_store import PaperAccountStore
from tradingbot.compliance.rules import FirmComplianceGate
from tradingbot.execution.router import ExecutionMode, ExecutionRouter
from tradingbot.models import Instrument
from tradingbot.paper.broker import PaperBroker
from tradingbot.risk.limits import RiskGuard, RiskLimits


class PaperAccountEngine:
    """Create only risk-gated routers backed by persisted PaperBroker fills."""

    def __init__(
        self,
        store: PaperAccountStore,
        risk_limits: RiskLimits,
        *,
        commission_per_contract_per_side_usd: float = 0.0,
        slippage_ticks_per_side: int = 1,
    ) -> None:
        if not isinstance(store, PaperAccountStore):
            raise TypeError("store must be a PaperAccountStore")
        if not isinstance(risk_limits, RiskLimits):
            raise TypeError("risk_limits must be RiskLimits")
        self.store = store
        self.commission = commission_per_contract_per_side_usd
        self.slippage_ticks = slippage_ticks_per_side
        self._risk_guard = RiskGuard(
            risk_limits,
            commission_per_contract_per_side_usd=commission_per_contract_per_side_usd,
            slippage_ticks_per_side=slippage_ticks_per_side,
        )
        self._brokers: dict[str, PaperBroker] = {}
        self._lock = threading.RLock()

    def _broker_for(self, instrument: Instrument) -> PaperBroker:
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        symbol = instrument.symbol.strip().upper()
        self.store.validate_instrument(instrument)
        with self._lock:
            existing = self._brokers.get(symbol)
            if existing is not None:
                if existing.instrument != instrument:
                    raise ValueError(
                        "Instrument specification changed for an existing broker; "
                        "reconcile open paper positions before restarting"
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

    def router_for(
        self,
        instrument: Instrument,
        *,
        compliance_gate: FirmComplianceGate | None = None,
        require_firm_profile: bool = True,
    ) -> ExecutionRouter:
        """Return a paper-only router. Firm-profile compliance is required by default.

        Setting require_firm_profile=False is an explicit research-only bypass of
        prop-firm checks; RiskGuard remains mandatory in either mode.
        """
        broker = self._broker_for(instrument)
        return ExecutionRouter(
            broker=broker,
            risk_guard=self._risk_guard,
            mode=ExecutionMode.PAPER,
            compliance_gate=compliance_gate,
            require_firm_profile=require_firm_profile,
        )

    @property
    def active_symbols(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._brokers))
