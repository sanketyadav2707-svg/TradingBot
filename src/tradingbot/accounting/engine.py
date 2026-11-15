"""Risk-gated composition layer for persistent local paper execution.

Only ExecutionRouter objects are exposed. Raw PaperBroker instances remain
private to this module so callers cannot accidentally skip risk/compliance gates.
This module never starts a strategy, market-data feed, scheduler or background loop.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from tradingbot.accounting.sqlite_store import PaperAccountStore
from tradingbot.compliance.rules import FirmComplianceGate
from tradingbot.execution.router import AccountRiskSnapshot, ExecutionMode, ExecutionRouter, OrderIntent
from tradingbot.execution.order_lifecycle import (
    BrokerSnapshot, OrderLifecycleStore, OrderState, ReconciliationReport,
)
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
        # Share the same durable SQLite database as accounting. Both journals
        # survive process restarts and are backed up as one account artifact.
        self.order_lifecycle = OrderLifecycleStore(store.path)
        self._backfill_accounting_fills()
        self._drain_lifecycle_outbox()
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
        self._execution_lock = threading.RLock()
        self._halt_event = threading.Event()
        if self.store.emergency_halt_active:
            self._halt_event.set()

    def _backfill_accounting_fills(self) -> None:
        """Rebuild lifecycle entries for legacy/accounting fills after interrupted writes."""
        offset = 0
        while True:
            rows = self.store.list_fills(limit=100, offset=offset)
            if not rows:
                break
            for row in rows:
                order_id = str(row["order_id"])
                existing = self.order_lifecycle.get_order(order_id)
                timestamp = datetime.fromisoformat(
                    str(row["timestamp"]).replace("Z", "+00:00")
                )
                if existing is not None and existing["state"] == "FILLED":
                    # A terminal state is not proof that both ledgers agree.
                    # Verify the exact execution before accepting startup recovery.
                    journal_fills = self.order_lifecycle.get_fills(order_id)
                    expected_timestamp = timestamp.astimezone(timezone.utc).isoformat(
                        timespec="microseconds"
                    ).replace("+00:00", "Z")
                    matches = (
                        len(journal_fills) == 1
                        and journal_fills[0]["fill_id"] == order_id
                        and int(journal_fills[0]["quantity"]) == int(row["quantity"])
                        and Decimal(str(journal_fills[0]["fill_price"])) == Decimal(str(row["fill_price"]))
                        and Decimal(str(journal_fills[0]["commission"])) == Decimal(str(row["commission_usd"]))
                        and str(journal_fills[0]["timestamp"]) == expected_timestamp
                        and int(existing["cumulative_filled"]) == int(row["quantity"])
                        and Decimal(str(existing["reference_price"])) == Decimal(str(row["requested_price"]))
                        and str(existing["symbol"]) == str(row["symbol"]).upper()
                        and str(existing["side"]) == str(row["side"]).upper()
                    )
                    if not matches:
                        raise RuntimeError(
                            f"accounting_lifecycle_fill_mismatch:{order_id}; "
                            "manual reconciliation is required before execution"
                        )
                    continue
                created = self.order_lifecycle.create_order(
                    client_order_id=order_id,
                    symbol=str(row["symbol"]),
                    side=str(row["side"]),
                    quantity=int(row["quantity"]),
                    reference_price=row["requested_price"],
                    timestamp=timestamp,
                )
                state = str(created["state"])
                # Accounting currently stores one aggregate fill per order ID.
                # Never add that aggregate on top of an existing journal execution.
                journal_fills = self.order_lifecycle.get_fills(order_id)
                if (
                    int(created["cumulative_filled"]) != 0
                    or journal_fills
                    or state not in {
                        OrderState.PENDING_SUBMIT.value,
                        OrderState.SUBMITTED.value,
                        OrderState.ACKNOWLEDGED.value,
                        OrderState.CANCEL_PENDING.value,
                        OrderState.UNKNOWN.value,
                    }
                ):
                    raise RuntimeError(
                        f"accounting_lifecycle_partial_or_state_mismatch:{order_id}; "
                        "manual reconciliation is required before execution"
                    )
                if state == OrderState.PENDING_SUBMIT.value:
                    self.order_lifecycle.transition(
                        order_id, OrderState.SUBMITTED, timestamp=timestamp
                    )
                self.order_lifecycle.record_fill(
                    client_order_id=order_id,
                    fill_id=order_id,
                    quantity=int(row["quantity"]),
                    fill_price=row["fill_price"],
                    commission=row["commission_usd"],
                    timestamp=timestamp,
                )
            offset += len(rows)
            if len(rows) < 100:
                break
        self._validate_lifecycle_against_accounting()

    def _drain_lifecycle_outbox(self) -> int:
        """Idempotently project accounting-committed fills into the lifecycle journal.

        The accounting fill and outbox row share one SQLite transaction. If this
        projection fails or the process stops, the pending row remains durable
        and is retried on the next startup or fill callback.
        """
        delivered = 0
        while True:
            pending = self.store.list_pending_lifecycle_outbox(limit=100)
            if not pending:
                break
            for row in pending:
                self.order_lifecycle.record_fill(
                    client_order_id=str(row["order_id"]),
                    fill_id=str(row["order_id"]),
                    quantity=int(row["quantity"]),
                    fill_price=row["fill_price"],
                    commission=row["commission_usd"],
                    timestamp=datetime.fromisoformat(
                        str(row["timestamp"]).replace("Z", "+00:00")
                    ),
                )
                self.store.mark_lifecycle_outbox_delivered(str(row["order_id"]))
                delivered += 1
        return delivered

    def _validate_lifecycle_against_accounting(self) -> None:
        """Fail closed if any journal execution is absent from or differs from accounting."""
        accounting_by_id: dict[str, dict[str, object]] = {}
        offset = 0
        while True:
            rows = self.store.list_fills(limit=100, offset=offset)
            if not rows:
                break
            for row in rows:
                order_id = str(row["order_id"])
                if order_id in accounting_by_id:
                    raise RuntimeError(
                        f"duplicate_accounting_order_id:{order_id}; manual reconciliation required"
                    )
                accounting_by_id[order_id] = row
            offset += len(rows)
            if len(rows) < 100:
                break

        offset = 0
        while True:
            orders = self.order_lifecycle.list_orders(limit=100, offset=offset)
            if not orders:
                break
            for order in orders:
                order_id = str(order["client_order_id"])
                journal_fills = self.order_lifecycle.get_fills(order_id)
                accounting = accounting_by_id.get(order_id)
                state = str(order["state"])
                if not journal_fills:
                    if state == OrderState.FILLED.value or int(order["cumulative_filled"]) != 0:
                        raise RuntimeError(
                            f"lifecycle_fill_missing_from_journal:{order_id}; manual reconciliation required"
                        )
                    continue
                if accounting is None:
                    raise RuntimeError(
                        f"lifecycle_fill_missing_from_accounting:{order_id}; "
                        "manual reconciliation is required before execution"
                    )
                if len(journal_fills) != 1 or state != OrderState.FILLED.value:
                    raise RuntimeError(
                        f"lifecycle_partial_fill_not_supported_by_accounting:{order_id}; "
                        "manual reconciliation is required before execution"
                    )
                fill = journal_fills[0]
                timestamp = datetime.fromisoformat(
                    str(accounting["timestamp"]).replace("Z", "+00:00")
                ).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
                matches = (
                    str(fill["fill_id"]) == order_id
                    and int(fill["quantity"]) == int(accounting["quantity"])
                    and Decimal(str(fill["fill_price"])) == Decimal(str(accounting["fill_price"]))
                    and Decimal(str(fill["commission"])) == Decimal(str(accounting["commission_usd"]))
                    and str(fill["timestamp"]) == timestamp
                    and int(order["cumulative_filled"]) == int(accounting["quantity"])
                    and Decimal(str(order["reference_price"])) == Decimal(str(accounting["requested_price"]))
                    and str(order["symbol"]) == str(accounting["symbol"]).upper()
                    and str(order["side"]) == str(accounting["side"]).upper()
                )
                if not matches:
                    raise RuntimeError(
                        f"lifecycle_accounting_fill_mismatch:{order_id}; "
                        "manual reconciliation is required before execution"
                    )
            offset += len(orders)
            if len(orders) < 100:
                break

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

            def persist_fill(fill) -> None:
                # Accounting is persisted first. Lifecycle persistence is then
                # idempotent and keyed by the broker fill ID. Any failure bubbles
                # up so PaperBroker does not acknowledge the simulated execution.
                self.store.record_fill(fill, instrument)
                self._drain_lifecycle_outbox()

            broker = PaperBroker(
                instrument,
                commission_per_contract_per_side_usd=self.commission,
                slippage_ticks_per_side=self.slippage_ticks,
                on_fill=persist_fill,
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
            halt_check=lambda: self._halt_event.is_set() or bool(self.order_lifecycle.list_unresolved_orders()),
            submission_lock=self._execution_lock,
            order_lifecycle=self.order_lifecycle,
        )

    def emergency_halt(self, reason: str = "manual_emergency_halt") -> None:
        """Durably block all routers, waiting for any in-flight paper submission.

        The SQLite latch is one-way. No method or API route clears it. A manual
        database-level recovery procedure with account reconciliation is required
        before a new paper account can resume execution.
        """
        with self._execution_lock:
            self._halt_event.set()
            self.store.activate_emergency_halt(reason)

    def reconcile_broker_snapshot(self, snapshot: BrokerSnapshot) -> ReconciliationReport:
        """Compare the durable local journal with an externally verified broker snapshot.

        This method never clears a halt or resolves unknown orders automatically.
        A non-safe report must be investigated before any manual journal correction.
        """
        return self.order_lifecycle.reconcile(snapshot)

    @property
    def recovery_required(self) -> bool:
        """True whenever a prior order outcome is unresolved."""
        return bool(self.order_lifecycle.list_unresolved_orders())

    @property
    def halted(self) -> bool:
        return self._halt_event.is_set() or self.store.emergency_halt_active

    @property
    def active_symbols(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._brokers))
