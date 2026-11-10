"""Risk-gated composition layer for persistent local paper execution.

Only ExecutionRouter objects are exposed. Raw PaperBroker instances remain
private to this module so callers cannot accidentally skip risk/compliance gates.
This module never starts a strategy, market-data feed, scheduler or background loop.
"""

from __future__ import annotations

import threading
from zoneinfo import ZoneInfo

from tradingbot.accounting.sqlite_store import PaperAccountStore
from tradingbot.compliance.rules import FirmComplianceGate
from tradingbot.execution.router import AccountRiskSnapshot, ExecutionMode, ExecutionRouter, OrderIntent
from tradingbot.models import Instrument
from tradingbot.paper.broker import PaperBroker
from tradingbot.risk.limits import RiskGuard, RiskLimits


class PaperAccountEngine:
    """Create paper-only routers whose fills persist before acknowledgement."""

    def __init__(
        self,
        store: PaperAccountStore,
        risk_limits: RiskLimits,
        *,
        commission_per_contract_per_side_usd: float = 0.0,
        slippage_ticks_per_side: int = 1,
        risk_timezone: str = "UTC",
        max_mark_age_seconds: int = 60,
    ) -> None:
        if not isinstance(store, PaperAccountStore):
            raise TypeError("store must be a PaperAccountStore")
        if not isinstance(risk_limits, RiskLimits):
            raise TypeError("risk_limits must be RiskLimits")
        self.store = store
        self.commission = commission_per_contract_per_side_usd
        self.slippage_ticks = slippage_ticks_per_side
        ZoneInfo(risk_timezone)
        if type(max_mark_age_seconds) is not int or max_mark_age_seconds < 1:
            raise ValueError("max_mark_age_seconds must be a positive integer")
        self.risk_timezone = risk_timezone
        self.max_mark_age_seconds = max_mark_age_seconds
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
        """Return a paper router. Firm compliance is fail-closed by default.

        Setting require_firm_profile=False is an explicit research-only bypass
        of prop-firm-profile checks. RiskGuard is mandatory in either mode.
        """
        risk_timezone = (
            compliance_gate.profile.timezone if compliance_gate is not None else self.risk_timezone
        )

        def account_snapshot_provider(intent: OrderIntent) -> AccountRiskSnapshot:
            values = self.store.get_risk_inputs(
                intent.timestamp,
                timezone_name=risk_timezone,
                max_mark_age_seconds=self.max_mark_age_seconds,
            )
            return AccountRiskSnapshot(**values)

        return ExecutionRouter(
            broker=self._broker_for(instrument),
            risk_guard=self._risk_guard,
            mode=ExecutionMode.PAPER,
            compliance_gate=compliance_gate,
            require_firm_profile=require_firm_profile,
            account_snapshot_provider=account_snapshot_provider,
        )

    @property
    def active_symbols(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._brokers))
