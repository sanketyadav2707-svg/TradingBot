"""Durable, fail-closed inbox for normalized closed market bars.

Phase 5 starts with a provider-neutral ingestion boundary. This module does not
open sockets or fetch data. A future authorized feed adapter normalizes provider
messages to Bar and appends them here before dispatch to the paper engine.

Dispatch is deliberately at-most-once. A process crash after claiming an event
leaves it DISPATCHING and blocks further dispatch until an operator reconciles
the paper ledger and explicitly resolves the event. Automatic replay could
duplicate a paper order if the crash occurred after the handler committed it.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tradingbot.models import Bar


class MarketDataInboxError(RuntimeError):
    """Base class for durable market-data inbox failures."""


class MarketDataInboxBlocked(MarketDataInboxError):
    """Dispatch is blocked pending operator reconciliation."""


class MarketDataConflict(MarketDataInboxError):
    """A provider reused an event key with different candle contents."""


@dataclass(frozen=True, slots=True)
class InboxEvent:
    event_id: int
    source_id: str
    bar: Bar
    received_at: datetime
    status: str


@dataclass(frozen=True, slots=True)
class InboxHealth:
    pending: int
    dispatching: int
    failed: int
    processed: int
    resolved: int
    oldest_pending_at: datetime | None
    ready: bool


class ClosedBarInbox:
    """SQLite-backed append-only event inbox with explicit crash recovery.

    The uniqueness key is (source_id, symbol, candle-open timestamp). Exact
    duplicate deliveries are idempotent. A conflicting duplicate is an error.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        max_pending_events: int = 10_000,
    ) -> None:
        if type(max_pending_events) is not int or max_pending_events < 1:
            raise ValueError("max_pending_events_must_be_positive_integer")
        self.path = str(database_path)
        self.max_pending_events = max_pending_events
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_data_inbox (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    bar_timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    received_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('PENDING','DISPATCHING','PROCESSED','FAILED','RESOLVED')
                    ),
                    error TEXT,
                    resolved_at TEXT,
                    resolution_reason TEXT,
                    UNIQUE(source_id, symbol, bar_timestamp)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_market_data_inbox_status_time
                ON market_data_inbox(status, event_id)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _aware(value: datetime, field: str) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field}_must_be_timezone_aware")
        return value.astimezone(timezone.utc)

    def enqueue(self, bar: Bar, *, source_id: str, received_at: datetime) -> int:
        if not isinstance(bar, Bar):
            raise TypeError("normalized_bar_required")
        if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 128:
            raise ValueError("source_id_must_contain_1_to_128_characters")
        stamp = self._aware(bar.timestamp, "bar_timestamp").isoformat(timespec="microseconds")
        received = self._aware(received_at, "received_at").isoformat(timespec="microseconds")
        normalized_symbol = bar.symbol.strip().upper()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            blocked = connection.execute(
                "SELECT status FROM market_data_inbox WHERE status IN ('DISPATCHING','FAILED') LIMIT 1"
            ).fetchone()
            if blocked is not None:
                connection.rollback()
                raise MarketDataInboxBlocked("inbox_requires_operator_reconciliation")
            pending = connection.execute(
                "SELECT COUNT(*) FROM market_data_inbox WHERE status='PENDING'"
            ).fetchone()[0]
            existing = connection.execute(
                """
                SELECT * FROM market_data_inbox
                WHERE source_id=? AND symbol=? AND bar_timestamp=?
                """,
                (source_id.strip(), normalized_symbol, stamp),
            ).fetchone()
            values = (
                float(bar.open), float(bar.high), float(bar.low),
                float(bar.close), float(bar.volume),
            )
            if existing is not None:
                old = tuple(existing[key] for key in ("open", "high", "low", "close", "volume"))
                if old != values:
                    connection.rollback()
                    raise MarketDataConflict("duplicate_event_key_has_conflicting_bar_payload")
                connection.commit()
                return int(existing["event_id"])
            if pending >= self.max_pending_events:
                connection.rollback()
                raise MarketDataInboxBlocked("market_data_inbox_backpressure_limit_reached")
            cursor = connection.execute(
                """
                INSERT INTO market_data_inbox(
                    source_id,symbol,bar_timestamp,open,high,low,close,volume,
                    received_at,status
                ) VALUES(?,?,?,?,?,?,?,?,?,'PENDING')
                """,
                (source_id.strip(), normalized_symbol, stamp, *values, received),
            )
            event_id = int(cursor.lastrowid)
            connection.commit()
            return event_id

    @staticmethod
    def _event(row: sqlite3.Row) -> InboxEvent:
        return InboxEvent(
            event_id=int(row["event_id"]),
            source_id=str(row["source_id"]),
            bar=Bar(
                timestamp=datetime.fromisoformat(row["bar_timestamp"]),
                symbol=str(row["symbol"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            ),
            received_at=datetime.fromisoformat(row["received_at"]),
            status=str(row["status"]),
        )

    def dispatch_next(self, handler: Callable[[Bar, datetime], object]) -> InboxEvent | None:
        """Claim and dispatch one event; never auto-retry ambiguous in-flight work."""
        if not callable(handler):
            raise TypeError("bar_handler_must_be_callable")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            blocked = connection.execute(
                "SELECT status FROM market_data_inbox WHERE status IN ('DISPATCHING','FAILED') LIMIT 1"
            ).fetchone()
            if blocked is not None:
                connection.rollback()
                raise MarketDataInboxBlocked("inbox_requires_operator_reconciliation")
            row = connection.execute(
                "SELECT * FROM market_data_inbox WHERE status='PENDING' ORDER BY event_id LIMIT 1"
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            event_id = int(row["event_id"])
            connection.execute(
                "UPDATE market_data_inbox SET status='DISPATCHING' WHERE event_id=? AND status='PENDING'",
                (event_id,),
            )
            event = self._event(row)
            connection.commit()

        try:
            handler(event.bar, event.received_at)
        except Exception as exc:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE market_data_inbox SET status='FAILED', error=? WHERE event_id=? AND status='DISPATCHING'",
                    (type(exc).__name__ + ":" + str(exc)[:500], event_id),
                )
            raise

        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE market_data_inbox SET status='PROCESSED', error=NULL WHERE event_id=? AND status='DISPATCHING'",
                (event_id,),
            )
            if cursor.rowcount != 1:
                raise MarketDataInboxBlocked("inbox_event_state_changed_during_dispatch")
        return InboxEvent(event.event_id, event.source_id, event.bar, event.received_at, "PROCESSED")

    def resolve_ambiguous_event(
        self,
        event_id: int,
        *,
        operator_reason: str,
        reconciled_at: datetime,
    ) -> None:
        """Resolve, but never replay, an ambiguous event after ledger reconciliation."""
        if type(event_id) is not int or event_id < 1:
            raise ValueError("event_id_must_be_positive_integer")
        if not isinstance(operator_reason, str) or not operator_reason.strip():
            raise ValueError("operator_reconciliation_reason_required")
        stamp = self._aware(reconciled_at, "reconciled_at").isoformat(timespec="microseconds")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE market_data_inbox
                SET status='RESOLVED', resolved_at=?, resolution_reason=?
                WHERE event_id=? AND status IN ('DISPATCHING','FAILED')
                """,
                (stamp, operator_reason.strip()[:500], event_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ValueError("only_dispatching_or_failed_events_can_be_resolved")
            connection.commit()

    def health(self) -> InboxHealth:
        with self._connect() as connection:
            counts = {
                row["status"]: int(row["count"])
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM market_data_inbox GROUP BY status"
                )
            }
            oldest = connection.execute(
                "SELECT MIN(received_at) FROM market_data_inbox WHERE status='PENDING'"
            ).fetchone()[0]
        pending = counts.get("PENDING", 0)
        dispatching = counts.get("DISPATCHING", 0)
        failed = counts.get("FAILED", 0)
        return InboxHealth(
            pending=pending,
            dispatching=dispatching,
            failed=failed,
            processed=counts.get("PROCESSED", 0),
            resolved=counts.get("RESOLVED", 0),
            oldest_pending_at=datetime.fromisoformat(oldest) if oldest else None,
            ready=dispatching == 0 and failed == 0 and pending < self.max_pending_events,
        )
