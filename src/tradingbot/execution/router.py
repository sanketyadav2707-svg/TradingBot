"""Risk- and compliance-gated order router.

The router is intentionally restricted to the concrete in-memory paper broker. A LIVE mode
or a custom broker implementation cannot be enabled by configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Callable
from uuid import uuid4

from tradingbot.execution.order_lifecycle import (
    OrderLifecycleError, OrderLifecycleStore, OrderState,
)

from tradingbot.compliance.rules import FirmComplianceGate
from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperBroker
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
    idempotency_key: str | None = None


class ExecutionRouter:
    """Routes an order only after risk/compliance approval and only through PaperBroker."""

    def __init__(
        self,
        *,
        broker: PaperBroker,
        risk_guard: RiskGuard,
        mode: ExecutionMode = ExecutionMode.PAPER,
        compliance_gate: FirmComplianceGate | None = None,
        require_firm_profile: bool = False,
        account_snapshot_provider: Callable[[OrderIntent], AccountRiskSnapshot] | None = None,
        halt_check: Callable[[], bool] | None = None,
        submission_lock: Any | None = None,
        order_lifecycle: OrderLifecycleStore | None = None,
    ) -> None:
        if type(broker) is not PaperBroker:
            raise TypeError("paper_broker_only: custom and live broker adapters are not supported")
        self._broker = broker
        self.risk_guard = risk_guard
        self.mode = mode
        self.compliance_gate = compliance_gate
        self.require_firm_profile = require_firm_profile
        self._account_snapshot_provider = account_snapshot_provider
        self._halt_check = halt_check
        self._submission_lock = submission_lock
        self._order_lifecycle = order_lifecycle
        self._halted = False

    def emergency_halt(self) -> None:
        """Permanently halt this router instance, waiting for an in-flight submit."""
        if self._submission_lock is None:
            self._halted = True
            return
        with self._submission_lock:
            self._halted = True

    def submit_entry(
        self,
        intent: OrderIntent,
        account: AccountRiskSnapshot | None = None,
    ) -> object:
        """Serialize entry evaluation and submission with an injected engine halt lock."""
        if self._submission_lock is None:
            return self._submit_entry_locked(intent, account)
        with self._submission_lock:
            return self._submit_entry_locked(intent, account)

    def _submit_entry_locked(
        self,
        intent: OrderIntent,
        account: AccountRiskSnapshot | None = None,
    ) -> object:
        if self._halted or (self._halt_check is not None and self._halt_check()):
            raise OrderRejected("emergency_halt_active")
        if self.mode != ExecutionMode.PAPER:
            raise OrderRejected("live_execution_not_implemented")
        if not isinstance(intent.side, Side) or intent.side not in (Side.LONG, Side.SHORT):
            raise OrderRejected("invalid_order_side")
        if (
            not isinstance(intent.timestamp, datetime)
            or intent.timestamp.tzinfo is None
            or intent.timestamp.utcoffset() is None
        ):
            raise OrderRejected("timestamp_must_be_timezone_aware")
        if intent.idempotency_key is not None and (
            not isinstance(intent.idempotency_key, str)
            or not intent.idempotency_key.strip()
            or len(intent.idempotency_key) > 128
        ):
            raise OrderRejected("idempotency_key_must_contain_1_to_128_characters")
        if (
            not isinstance(intent.reference_price, (int, float))
            or isinstance(intent.reference_price, bool)
            or not isfinite(intent.reference_price)
        ):
            raise OrderRejected("reference_price_must_be_finite")

        broker_instrument = self._broker.instrument
        requested_instrument = intent.instrument
        same_contract = (
            broker_instrument.symbol.strip().upper()
            == requested_instrument.symbol.strip().upper()
        )
        same_specification = (
            broker_instrument.tick_size == requested_instrument.tick_size
            and broker_instrument.tick_value_usd == requested_instrument.tick_value_usd
            and broker_instrument.point_value_usd == requested_instrument.point_value_usd
        )
        if not same_contract or not same_specification:
            raise OrderRejected("broker_instrument_mismatch")
        if self.require_firm_profile and self.compliance_gate is None:
            raise OrderRejected("verified_firm_profile_required")

        if self._account_snapshot_provider is not None:
            if account is not None:
                raise OrderRejected("externally_supplied_account_snapshot_not_allowed")
            try:
                account = self._account_snapshot_provider(intent)
            except Exception as exc:
                raise OrderRejected(f"account_risk_snapshot_unavailable:{exc}") from exc
        elif account is None:
            raise OrderRejected("account_risk_snapshot_required")

        if not isinstance(account, AccountRiskSnapshot):
            raise OrderRejected("invalid_account_snapshot_type")

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

        if self._order_lifecycle is None:
            return self._broker.submit_market(
                side=intent.side,
                quantity=decision.quantity,
                reference_price=intent.reference_price,
                timestamp=intent.timestamp,
                order_id=intent.idempotency_key,
            )

        # A durable idempotency key is mandatory when journaling is enabled.
        # Never manufacture a new key for a retryable strategy signal.
        if intent.idempotency_key is None:
            raise OrderRejected("durable_order_idempotency_key_required")
        journal = self._order_lifecycle
        try:
            created = journal.create_order(
                client_order_id=intent.idempotency_key,
                symbol=intent.instrument.symbol,
                side="LONG" if intent.side == Side.LONG else "SHORT",
                quantity=decision.quantity,
                reference_price=intent.reference_price,
                timestamp=intent.timestamp,
            )
        except (ValueError, OrderLifecycleError) as exc:
            raise OrderRejected(f"durable_order_intent_rejected:{exc}") from exc

        state = OrderState(str(created["state"]))
        if not bool(created.get("_created", False)):
            # Completed order retry: reconstruct the original receipt. Never resubmit.
            if state == OrderState.FILLED:
                fills = journal.get_fills(intent.idempotency_key)
                if int(created["cumulative_filled"]) != int(created["quantity"]) or len(fills) != 1:
                    raise OrderRejected("completed_order_fill_history_requires_manual_reconciliation")
                item = fills[0]
                from tradingbot.paper.broker import PaperFill
                return PaperFill(
                    order_id=intent.idempotency_key,
                    symbol=str(created["symbol"]),
                    side=Side.LONG if created["side"] == "LONG" else Side.SHORT,
                    quantity=int(item["quantity"]),
                    requested_price=float(created["reference_price"]),
                    fill_price=float(item["fill_price"]),
                    commission_usd=float(item["commission"]),
                    timestamp=datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")),
                )
            raise OrderRejected(f"existing_order_not_resubmitted:{state.value}")

        try:
            journal.transition(
                intent.idempotency_key, OrderState.SUBMITTED, timestamp=intent.timestamp
            )
            return self._broker.submit_market(
                side=intent.side,
                quantity=decision.quantity,
                reference_price=intent.reference_price,
                timestamp=intent.timestamp,
                order_id=intent.idempotency_key,
            )
        except Exception as exc:
            current = journal.get_order(intent.idempotency_key)
            if current is not None and current["state"] == OrderState.SUBMITTED.value:
                try:
                    journal.transition(
                        intent.idempotency_key, OrderState.UNKNOWN,
                        timestamp=datetime.now(intent.timestamp.tzinfo),
                        reason="paper_submission_or_persistence_outcome_uncertain",
                    )
                except Exception:
                    pass
            if isinstance(exc, OrderRejected):
                raise
            raise OrderRejected("order_outcome_unknown_entries_blocked") from exc
