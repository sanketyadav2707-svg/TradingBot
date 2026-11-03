"""Risk- and compliance-gated order router.

The router is intentionally restricted to the in-memory paper broker. A LIVE mode cannot
be enabled by configuration; a future live adapter requires a separate, reviewed change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from tradingbot.compliance.rules import FirmComplianceGate
from tradingbot.execution.ports import ExecutionPort
from tradingbot.models import Instrument, Side
from tradingbot.risk.limits import RiskGuard


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class OrderRejected(RuntimeError):
    """Raised when an order fails a risk, compliance or operating-state gate."""


@dataclass(frozen=True, slots=True)
class AccountRiskSnapshot:
    equity_usd: float
    peak_equity_usd: float
    daily_pnl_usd: float
    trades_today: int


@dataclass(frozen=True, slots=True)
class OrderIntent:
    instrument: Instrument
    side: Side
    stop_ticks: int
    reference_price: float
    timestamp: datetime


class ExecutionRouter:
    """Routes an order only after risk/compliance approval and only in paper mode."""

    def __init__(
        self,
        *,
        broker: ExecutionPort,
        risk_guard: RiskGuard,
        mode: ExecutionMode = ExecutionMode.PAPER,
        compliance_gate: FirmComplianceGate | None = None,
        require_firm_profile: bool = False,
    ) -> None:
        self.broker = broker
        self.risk_guard = risk_guard
        self.mode = mode
        self.compliance_gate = compliance_gate
        self.require_firm_profile = require_firm_profile
        self._halted = False

    def emergency_halt(self) -> None:
        """Permanently halt this router instance. Restart/review is required to resume."""
        self._halted = True

    def submit_entry(self, intent: OrderIntent, account: AccountRiskSnapshot) -> object:
        if self._halted:
            raise OrderRejected("emergency_halt_active")
        if self.mode != ExecutionMode.PAPER:
            raise OrderRejected("live_execution_not_implemented")
        if intent.side == Side.FLAT:
            raise OrderRejected("flat_side_cannot_be_submitted")
        if intent.instrument.symbol.strip().upper() == "":
            raise OrderRejected("instrument_symbol_missing")
        if self.broker.instrument.symbol.upper() != intent.instrument.symbol.upper():
            raise OrderRejected("broker_instrument_mismatch")
        if self.require_firm_profile and self.compliance_gate is None:
            raise OrderRejected("verified_firm_profile_required")

        decision = self.risk_guard.evaluate_entry(
            instrument=intent.instrument,
            stop_ticks=intent.stop_ticks,
            equity_usd=account.equity_usd,
            peak_equity_usd=account.peak_equity_usd,
            daily_pnl_usd=account.daily_pnl_usd,
            trades_today=account.trades_today,
        )
        if not decision.approved:
            raise OrderRejected(decision.reason)

        if self.compliance_gate is not None:
            compliance = self.compliance_gate.check_entry(
                timestamp=intent.timestamp,
                symbol=intent.instrument.symbol,
                quantity=decision.quantity,
            )
            if not compliance.allowed:
                raise OrderRejected(compliance.reason)

        return self.broker.submit_market(
            side=intent.side,
            quantity=decision.quantity,
            reference_price=intent.reference_price,
            timestamp=intent.timestamp,
        )
