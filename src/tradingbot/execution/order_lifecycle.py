"""Durable order lifecycle and fail-closed broker reconciliation.

This module records order intent before submission and keeps an append-only
transition/fill journal. It is broker-neutral but does not implement a live
broker adapter. Reconciliation consumes an authoritative broker snapshot.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Iterator, Mapping


class OrderState(str, Enum):
    PENDING_SUBMIT = "PENDING_SUBMIT"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


_TERMINAL = {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED}
_OPEN = {
    OrderState.PENDING_SUBMIT, OrderState.SUBMITTED, OrderState.ACKNOWLEDGED,
    OrderState.PARTIALLY_FILLED, OrderState.CANCEL_PENDING, OrderState.UNKNOWN,
}
_ALLOWED = {
    OrderState.PENDING_SUBMIT: {OrderState.SUBMITTED, OrderState.REJECTED, OrderState.UNKNOWN},
    OrderState.SUBMITTED: {OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED,
                           OrderState.FILLED, OrderState.CANCEL_PENDING,
                           OrderState.CANCELLED, OrderState.REJECTED, OrderState.UNKNOWN},
    OrderState.ACKNOWLEDGED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                              OrderState.CANCEL_PENDING, OrderState.CANCELLED,
                              OrderState.REJECTED, OrderState.UNKNOWN},
    OrderState.PARTIALLY_FILLED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                                  OrderState.CANCEL_PENDING, OrderState.CANCELLED,
                                  OrderState.UNKNOWN},
    OrderState.CANCEL_PENDING: {OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                                OrderState.CANCELLED, OrderState.UNKNOWN},
    OrderState.UNKNOWN: {OrderState.SUBMITTED, OrderState.ACKNOWLEDGED,
                         OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                         OrderState.CANCEL_PENDING, OrderState.CANCELLED,
                         OrderState.REJECTED},
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
}


class OrderLifecycleError(RuntimeError):
    """An order transition or lifecycle operation violates safety invariants."""


class DuplicateOrderError(OrderLifecycleError):
    """A client order ID was reused with a different order payload."""


def _utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp_must_be_timezone_aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label}_must_be_finite")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}_must_be_finite") from exc
    if not result.is_finite():
        raise ValueError(f"{label}_must_be_finite")
    return result


def _canonical_payload(symbol: str, side: str, quantity: int, reference_price: Decimal) -> str:
    return json.dumps({
        "symbol": symbol, "side": side, "quantity": quantity,
        "reference_price": format(reference_price.normalize(), "f"),
    }, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class BrokerSnapshot:
    """Authoritative broker state; quantities are signed net contracts by symbol."""
    positions: Mapping[str, int]
    open_order_ids: frozenset[str]
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    safe_to_trade: bool
    position_mismatches: Mapping[str, tuple[int, int]]
    broker_only_orders: tuple[str, ...]
    local_only_orders: tuple[str, ...]
    unresolved_orders: tuple[str, ...]
    observed_at: str

    @property
    def reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.position_mismatches:
            reasons.append("position_mismatch")
        if self.broker_only_orders:
            reasons.append("broker_only_open_orders")
        if self.local_only_orders:
            reasons.append("local_only_open_orders")
        if self.unresolved_orders:
            reasons.append("unresolved_local_orders")
        return tuple(reasons)


class OrderLifecycleStore:
    """SQLite-backed order journal. Reuse the account database path when possible."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path).expanduser().resolve()
        if str(database_path) == ":memory:":
            raise ValueError("Use a persistent SQLite file for order lifecycle state")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS order_intents (
                    client_order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('LONG','SHORT')),
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    reference_price TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    cumulative_filled INTEGER NOT NULL DEFAULT 0 CHECK(cumulative_filled >= 0),
                    average_fill_price TEXT,
                    last_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_order_intents_state
                    ON order_intents(state, updated_at);
                CREATE TABLE IF NOT EXISTS order_lifecycle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_order_id TEXT NOT NULL REFERENCES order_intents(client_order_id),
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    reason TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_order_events_order
                    ON order_lifecycle_events(client_order_id, id);
                CREATE TABLE IF NOT EXISTS order_fills (
                    fill_id TEXT PRIMARY KEY,
                    client_order_id TEXT NOT NULL REFERENCES order_intents(client_order_id),
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    fill_price TEXT NOT NULL,
                    commission TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
            """)

    def create_order(
        self, *, client_order_id: str, symbol: str, side: str, quantity: int,
        reference_price: object, timestamp: datetime,
    ) -> dict[str, object]:
        if not isinstance(client_order_id, str) or not client_order_id.strip() or len(client_order_id) > 128:
            raise ValueError("client_order_id_must_contain_1_to_128_characters")
        normalized_id = client_order_id.strip()
        normalized_symbol = str(symbol).strip().upper()
        normalized_side = str(side).strip().upper()
        if not normalized_symbol or len(normalized_symbol) > 32:
            raise ValueError("symbol_must_contain_1_to_32_characters")
        if normalized_side not in {"LONG", "SHORT"}:
            raise ValueError("side_must_be_LONG_or_SHORT")
        if type(quantity) is not int or not 1 <= quantity <= 100:
            raise ValueError("quantity_must_be_integer_between_1_and_100")
        price = _decimal(reference_price, "reference_price")
        stamp = _utc(timestamp)
        payload = _canonical_payload(normalized_symbol, normalized_side, quantity, price)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM order_intents WHERE client_order_id = ?", (normalized_id,)
            ).fetchone()
            if existing is not None:
                if existing["payload_hash"] != digest:
                    raise DuplicateOrderError("client_order_id_reused_with_different_payload")
                return self._order_dict(existing)
            connection.execute(
                """INSERT INTO order_intents(
                    client_order_id,symbol,side,quantity,reference_price,payload_hash,
                    state,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (normalized_id, normalized_symbol, normalized_side, quantity,
                 format(price.normalize(), "f"), digest, OrderState.PENDING_SUBMIT.value, stamp, stamp),
            )
            self._event(connection, normalized_id, "ORDER_CREATED", stamp, None, {
                "symbol": normalized_symbol, "side": normalized_side,
                "quantity": quantity, "reference_price": format(price.normalize(), "f"),
            })
            row = connection.execute(
                "SELECT * FROM order_intents WHERE client_order_id = ?", (normalized_id,)
            ).fetchone()
            return self._order_dict(row)

    @staticmethod
    def _event(connection: sqlite3.Connection, order_id: str, event: str,
               stamp: str, reason: str | None, payload: Mapping[str, object]) -> None:
        connection.execute(
            """INSERT INTO order_lifecycle_events(
                client_order_id,event_type,timestamp,reason,payload_json
            ) VALUES (?,?,?,?,?)""",
            (order_id, event, stamp, reason, json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        )

    @staticmethod
    def _order_dict(row: sqlite3.Row) -> dict[str, object]:
        return {
            "client_order_id": row["client_order_id"], "symbol": row["symbol"],
            "side": row["side"], "quantity": row["quantity"],
            "reference_price": row["reference_price"], "state": row["state"],
            "cumulative_filled": row["cumulative_filled"],
            "average_fill_price": row["average_fill_price"],
            "last_reason": row["last_reason"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def transition(
        self, client_order_id: str, state: OrderState, *, timestamp: datetime,
        reason: str | None = None,
    ) -> dict[str, object]:
        if not isinstance(state, OrderState):
            raise TypeError("state_must_be_OrderState")
        if reason is not None and (not isinstance(reason, str) or len(reason) > 256):
            raise ValueError("reason_must_be_at_most_256_characters")
        stamp = _utc(timestamp)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM order_intents WHERE client_order_id = ?", (client_order_id,)
            ).fetchone()
            if row is None:
                raise KeyError("unknown_client_order_id")
            current = OrderState(row["state"])
            if state == current:
                return self._order_dict(row)
            if state not in _ALLOWED[current]:
                raise OrderLifecycleError(f"invalid_order_transition:{current.value}->{state.value}")
            if state == OrderState.FILLED and int(row["cumulative_filled"]) != int(row["quantity"]):
                raise OrderLifecycleError("cannot_mark_filled_before_full_cumulative_quantity")
            connection.execute(
                "UPDATE order_intents SET state=?,last_reason=?,updated_at=? WHERE client_order_id=?",
                (state.value, reason, stamp, client_order_id),
            )
            self._event(connection, client_order_id, state.value, stamp, reason, {})
            updated = connection.execute(
                "SELECT * FROM order_intents WHERE client_order_id = ?", (client_order_id,)
            ).fetchone()
            return self._order_dict(updated)

    def record_fill(
        self, *, client_order_id: str, fill_id: str, quantity: int,
        fill_price: object, commission: object, timestamp: datetime,
    ) -> dict[str, object]:
        if not isinstance(fill_id, str) or not fill_id.strip() or len(fill_id) > 128:
            raise ValueError("fill_id_must_contain_1_to_128_characters")
        if type(quantity) is not int or quantity < 1:
            raise ValueError("fill_quantity_must_be_positive_integer")
        price = _decimal(fill_price, "fill_price")
        fee = _decimal(commission, "commission")
        if fee < 0:
            raise ValueError("commission_must_be_non_negative")
        stamp = _utc(timestamp)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM order_intents WHERE client_order_id = ?", (client_order_id,)
            ).fetchone()
            if row is None:
                raise KeyError("unknown_client_order_id")
            existing = connection.execute(
                "SELECT * FROM order_fills WHERE fill_id = ?", (fill_id.strip(),)
            ).fetchone()
            candidate = (client_order_id, quantity, format(price.normalize(), "f"),
                         format(fee.normalize(), "f"), stamp)
            if existing is not None:
                actual = (existing["client_order_id"], existing["quantity"],
                          existing["fill_price"], existing["commission"], existing["timestamp"])
                if actual != candidate:
                    raise DuplicateOrderError("fill_id_reused_with_different_execution_data")
                return self._order_dict(row)
            current = OrderState(row["state"])
            if current not in _OPEN:
                raise OrderLifecycleError("fill_rejected_for_non_open_order")
            cumulative = int(row["cumulative_filled"]) + quantity
            requested = int(row["quantity"])
            if cumulative > requested:
                raise OrderLifecycleError("cumulative_fill_exceeds_order_quantity")
            prior_qty = int(row["cumulative_filled"])
            prior_avg = Decimal(row["average_fill_price"] or "0")
            average = ((prior_avg * prior_qty) + (price * quantity)) / Decimal(cumulative)
            next_state = OrderState.FILLED if cumulative == requested else OrderState.PARTIALLY_FILLED
            if next_state not in _ALLOWED[current] and next_state != current:
                raise OrderLifecycleError(f"invalid_order_transition:{current.value}->{next_state.value}")
            connection.execute(
                """INSERT INTO order_fills(fill_id,client_order_id,quantity,fill_price,commission,timestamp)
                   VALUES (?,?,?,?,?,?)""",
                (fill_id.strip(), *candidate),
            )
            connection.execute(
                """UPDATE order_intents SET cumulative_filled=?,average_fill_price=?,
                   state=?,updated_at=?,last_reason=NULL WHERE client_order_id=?""",
                (cumulative, format(average.normalize(), "f"), next_state.value, stamp, client_order_id),
            )
            self._event(connection, client_order_id, "FILL_RECORDED", stamp, None, {
                "fill_id": fill_id.strip(), "quantity": quantity,
                "fill_price": format(price.normalize(), "f"),
                "cumulative_filled": cumulative, "state": next_state.value,
            })
            updated = connection.execute(
                "SELECT * FROM order_intents WHERE client_order_id = ?", (client_order_id,)
            ).fetchone()
            return self._order_dict(updated)

    def get_order(self, client_order_id: str) -> dict[str, object] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM order_intents WHERE client_order_id = ?", (client_order_id,)
            ).fetchone()
        return self._order_dict(row) if row is not None else None

    def list_orders(self, *, limit: int = 100) -> list[dict[str, object]]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit_must_be_between_1_and_1000")
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM order_intents ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._order_dict(row) for row in rows]

    def list_events(self, client_order_id: str) -> list[dict[str, object]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM order_lifecycle_events
                   WHERE client_order_id=? ORDER BY id""", (client_order_id,)
            ).fetchall()
        return [{
            "id": row["id"], "event_type": row["event_type"],
            "timestamp": row["timestamp"], "reason": row["reason"],
            "payload": json.loads(row["payload_json"]),
        } for row in rows]

    def reconcile(self, snapshot: BrokerSnapshot) -> ReconciliationReport:
        if not isinstance(snapshot, BrokerSnapshot):
            raise TypeError("snapshot_must_be_BrokerSnapshot")
        observed = _utc(snapshot.observed_at)
        broker_positions: dict[str, int] = {}
        for symbol, quantity in snapshot.positions.items():
            key = str(symbol).strip().upper()
            if not key or type(quantity) is not int:
                raise ValueError("broker_snapshot_positions_must_be_integer_quantities")
            if key in broker_positions:
                raise ValueError("duplicate_normalized_broker_position_symbol")
            if quantity:
                broker_positions[key] = quantity
        broker_orders = frozenset(snapshot.open_order_ids)
        if any(not isinstance(item, str) or not item.strip() for item in broker_orders):
            raise ValueError("broker_open_order_ids_must_be_non_empty_strings")

        with self._lock, self._connection() as connection:
            fills = connection.execute(
                """SELECT o.symbol,o.side,f.quantity FROM order_fills f
                   JOIN order_intents o ON o.client_order_id=f.client_order_id"""
            ).fetchall()
            local_orders = connection.execute(
                "SELECT client_order_id,state FROM order_intents"
            ).fetchall()

        local_positions: dict[str, int] = {}
        for fill in fills:
            sign = 1 if fill["side"] == "LONG" else -1
            local_positions[fill["symbol"]] = local_positions.get(fill["symbol"], 0) + sign * int(fill["quantity"])
        all_symbols = set(local_positions) | set(broker_positions)
        mismatches = {
            symbol: (local_positions.get(symbol, 0), broker_positions.get(symbol, 0))
            for symbol in sorted(all_symbols)
            if local_positions.get(symbol, 0) != broker_positions.get(symbol, 0)
        }
        local_open = {
            row["client_order_id"] for row in local_orders
            if OrderState(row["state"]) in _OPEN
        }
        unresolved = {
            row["client_order_id"] for row in local_orders
            if OrderState(row["state"]) in {OrderState.UNKNOWN, OrderState.PENDING_SUBMIT, OrderState.SUBMITTED}
        }
        broker_only = broker_orders - local_open
        local_only = local_open - broker_orders
        safe = not (mismatches or broker_only or local_only or unresolved)
        return ReconciliationReport(
            safe_to_trade=safe,
            position_mismatches=mismatches,
            broker_only_orders=tuple(sorted(broker_only)),
            local_only_orders=tuple(sorted(local_only)),
            unresolved_orders=tuple(sorted(unresolved)),
            observed_at=observed,
        )
