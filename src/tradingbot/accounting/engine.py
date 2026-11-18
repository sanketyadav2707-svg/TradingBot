"""Risk-gated composition layer for persistent local paper execution.

Only ExecutionRouter objects are exposed. Raw PaperBroker instances remain
private to this module so callers cannot accidentally skip risk/compliance gates.
This module never starts a strategy, market-data feed, scheduler or background loop.
"""

from __future__ import annotations

import fcntl
import hashlib
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
from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperBroker
from tradingbot.money import FeeSchedule
from tradingbot.risk.limits import RiskGuard, RiskLimits


class _AccountExecutionLock:
    """Serialize risk-check-to-fill sections across threads and local processes.

    The lock file is stable for the lifetime of the account database. POSIX
    advisory locks are released by the OS if a process exits or crashes.
    Keep the lock file; unlinking it while another process holds it can split
    the lock into two independent inodes.
    """

    def __init__(self, database_path) -> None:
        self.path = database_path.with_name(database_path.name + ".execution.lock")
        self._thread_lock = threading.RLock()

    def __enter__(self):
        self._thread_lock.acquire()
        try:
            self._handle = self.path.open("a+b")
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
            return self
        except BaseException:
            handle = getattr(self, "_handle", None)
            if handle is not None:
                handle.close()
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
        finally:
            self._thread_lock.release()


class PaperAccountEngine:
    """Create paper-only routers whose fills persist before acknowledgement."""

    def __init__(
        self,
        store: PaperAccountStore,
        risk_limits: RiskLimits,
        *,
        commission_per_contract_per_side_usd: float = 0.0,
        slippage_ticks_per_side: int = 1,
        fee_schedule: FeeSchedule | None = None,
        risk_timezone: str = "UTC",
        max_mark_age_seconds: int = 60,
    ) -> None:
        if not isinstance(store, PaperAccountStore):
            raise TypeError("store must be a PaperAccountStore")
        if not isinstance(risk_limits, RiskLimits):
            raise TypeError("risk_limits must be RiskLimits")
        if store.currency_code != risk_limits.currency_code:
            raise ValueError("paper account and risk-limit currencies must match")
        self.store = store
        # Share the same durable SQLite database as accounting. Both journals
        # survive process restarts and are backed up as one account artifact.
        self.order_lifecycle = OrderLifecycleStore(store.path)
        self._backfill_accounting_fills()
        self._drain_lifecycle_outbox()
        if fee_schedule is not None and fee_schedule.currency != store.currency_code:
            raise ValueError("fee_schedule_currency_mismatch")
        self.fee_schedule = fee_schedule
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
            fee_schedule=fee_schedule,
        )
        self._brokers: dict[str, PaperBroker] = {}
        self._lock = threading.RLock()
        self._execution_lock = _AccountExecutionLock(store.path)
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
        if instrument.currency_code != self.store.currency_code:
            raise ValueError("instrument currency does not match paper account currency")
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
                fee_schedule=self.fee_schedule,
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
            return AccountRiskSnapshot(**values, currency_code=self.store.currency_code)

        return ExecutionRouter(
            broker=self._broker_for(instrument),
            risk_guard=self._risk_guard,
            mode=ExecutionMode.PAPER,
            compliance_gate=compliance_gate,
            require_firm_profile=require_firm_profile,
            account_snapshot_provider=account_snapshot_provider,
            halt_check=lambda: (
                self._halt_event.is_set()
                or self.store.emergency_halt_active
                or bool(self.order_lifecycle.list_unresolved_orders())
            ),
            submission_lock=self._execution_lock,
            order_lifecycle=self.order_lifecycle,
        )

    def close_position(
        self,
        instrument: Instrument,
        *,
        reference_price: float,
        timestamp: datetime,
    ) -> tuple:
        """Flatten the complete open position using paper fills, even during a halt.

        This is an exit-only path: it cannot create a position from flat. It bypasses
        entry risk limits because reducing exposure must remain possible after a halt,
        but still requires a verified instrument, fresh caller-supplied price/time,
        no unresolved order states, exchange quantity-step compliance and durable
        accounting/lifecycle persistence. Oversized positions are sliced below freeze.
        """
        if not isinstance(instrument, Instrument):
            raise TypeError("position_close_instrument_must_be_Instrument")
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("position_close_timestamp_must_be_timezone_aware")
        try:
            price = Decimal(str(reference_price))
        except Exception as exc:
            raise ValueError("position_close_reference_price_must_be_finite") from exc
        if not price.is_finite():
            raise ValueError("position_close_reference_price_must_be_finite")

        with self._execution_lock:
            if self.order_lifecycle.list_unresolved_orders():
                raise RuntimeError("unresolved_orders_block_position_close")
            symbol = instrument.symbol.strip().upper()
            positions = [
                position for position in self.store.list_positions()
                if str(position["symbol"]).strip().upper() == symbol
            ]
            if not positions:
                raise ValueError("no_open_position_for_symbol")
            if len(positions) != 1:
                raise RuntimeError("position_ledger_not_unique_for_symbol")
            position = positions[0]
            if position["side"] not in {"LONG", "SHORT"}:
                raise RuntimeError("position_ledger_side_invalid")
            remaining = int(position["quantity"])
            if remaining <= 0:
                raise RuntimeError("open_position_quantity_invalid")
            exit_side = Side.SHORT if position["side"] == "LONG" else Side.LONG
            broker = self._broker_for(instrument)
            max_slice = instrument.quantity_freeze - (
                instrument.quantity_freeze % instrument.quantity_step
            )
            if max_slice < instrument.lot_size:
                raise RuntimeError("instrument_freeze_below_quantity_step")
            original_quantity = remaining
            fills = []
            slice_index = 0
            while remaining:
                quantity = min(remaining, max_slice)
                quantity -= quantity % instrument.quantity_step
                if quantity < instrument.lot_size:
                    raise RuntimeError("remaining_position_cannot_be_sliced_to_valid_quantity")
                identity = "|".join((
                    "paper-close",
                    symbol,
                    str(position["opened_at"]),
                    str(original_quantity),
                    str(remaining),
                    str(slice_index),
                    timestamp.astimezone(timezone.utc).isoformat(timespec="microseconds"),
                    format(price, "f"),
                ))
                client_order_id = "close-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:48]
                fills.append(broker.submit_market(
                    side=exit_side,
                    quantity=quantity,
                    reference_price=float(price),
                    timestamp=timestamp,
                    order_id=client_order_id,
                ))
                remaining -= quantity
                slice_index += 1
            return tuple(fills)

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
