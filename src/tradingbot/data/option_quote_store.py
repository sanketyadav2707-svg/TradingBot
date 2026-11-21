"""Durable normalized option bid/ask tick journal for offline research.

No Upstox connection is created. An authenticated decoder must supply
instrument-bound OptionQuote snapshots and a nonempty provenance label.
Same instrument + exchange timestamp with different contents fails closed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tradingbot.risk.index_options import OptionQuote, aware, option_quote_fingerprint


class OptionTickJournalError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TickReceipt:
    instrument_key: str
    source: str
    timestamp: datetime
    snapshot_sha256: str
    duplicate: bool


class OptionTickJournal:
    """Serializes full option quote snapshots without converting Decimal to float."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = str(database_path)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS option_quote_ticks (
                    instrument_key TEXT NOT NULL,
                    exchange_timestamp TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    quote_json TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    PRIMARY KEY(instrument_key, exchange_timestamp)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_option_quote_source ON option_quote_ticks(source_id, received_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA synchronous=FULL")
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _serialize(quote: OptionQuote) -> str:
        data = {
            "instrument_key": quote.instrument_key,
            "timestamp": aware(quote.timestamp, "timestamp").isoformat(timespec="microseconds"),
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "bid_quantity": quote.bid_quantity,
            "ask_quantity": quote.ask_quantity,
            "underlying_price": str(quote.underlying_price),
            "underlying_timestamp": aware(quote.underlying_timestamp, "underlying_timestamp").isoformat(timespec="microseconds"),
            "implied_volatility": str(quote.implied_volatility),
            "open_interest": quote.open_interest,
            "trading_halted": quote.trading_halted,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def record(
        self,
        *,
        quote: OptionQuote,
        source_id: str,
        received_at: datetime,
    ) -> TickReceipt:
        if not isinstance(quote, OptionQuote):
            raise TypeError("option_quote_required")
        if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 128:
            raise ValueError("source_id_required")
        stamp = aware(quote.timestamp, "quote_timestamp")
        observed_at = aware(received_at, "received_at")
        if observed_at < stamp:
            raise OptionTickJournalError("tick_received_before_exchange_timestamp")
        text = self._serialize(quote)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        # Digest includes all quote fields and is different from the risk gate
        # fingerprint's salt-free format; both identify complete snapshots.
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT source_id,snapshot_sha256 FROM option_quote_ticks WHERE instrument_key=? AND exchange_timestamp=?",
                (quote.instrument_key, stamp.isoformat(timespec="microseconds")),
            ).fetchone()
            if existing is not None:
                if existing["snapshot_sha256"] != digest or existing["source_id"] != source_id.strip():
                    conn.rollback()
                    raise OptionTickJournalError("conflicting_option_quote_tick")
                conn.commit()
                return TickReceipt(quote.instrument_key, source_id.strip(), stamp, digest, True)
            conn.execute(
                """
                INSERT INTO option_quote_ticks(
                    instrument_key,exchange_timestamp,source_id,received_at,
                    quote_json,snapshot_sha256
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    quote.instrument_key, stamp.isoformat(timespec="microseconds"),
                    source_id.strip(), observed_at.isoformat(timespec="microseconds"),
                    text, digest,
                ),
            )
            conn.commit()
        return TickReceipt(quote.instrument_key, source_id.strip(), stamp, digest, False)

    def count(self, instrument_key: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM option_quote_ticks WHERE instrument_key=?",
                (instrument_key,),
            ).fetchone()
        return int(row[0])

    def latest_snapshot(self, instrument_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT quote_json FROM option_quote_ticks
                WHERE instrument_key=? ORDER BY exchange_timestamp DESC LIMIT 1
                """,
                (instrument_key,),
            ).fetchone()
        return json.loads(row[0]) if row else None
