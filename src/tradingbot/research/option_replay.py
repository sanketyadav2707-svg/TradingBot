"""Point-in-time option research input from the normalized SQLite journal.

Only snapshots actually received by the decision cutoff are eligible.
This is offline research, not proof of market-data authenticity.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from tradingbot.risk.index_options import OptionQuote, aware


class OptionReplayError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReplaySnapshot:
    quote: OptionQuote
    received_at: datetime
    source_id: str
    sha256: str


def load_option_replay(
    database_path: str | Path, *, instrument_key: str, source_id: str,
    start: datetime, end: datetime, max_rows: int = 100_000,
) -> tuple[ReplaySnapshot, ...]:
    """Read a bounded interval of receipt times, ordered by availability.

    Verify journal payload hashes and metadata. Reject inconsistent or
    out-of-order exchange snapshots rather than silently repairing them.
    """
    begin, finish = aware(start, "start"), aware(end, "end")
    if begin >= finish or type(max_rows) is not int or not 1 <= max_rows <= 1_000_000:
        raise ValueError("invalid_replay_window_or_limit")
    if not instrument_key.strip() or not source_id.strip():
        raise ValueError("instrument_and_source_required")
    uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM option_quote_ticks
               WHERE instrument_key=? AND source_id=? AND received_at>=? AND received_at<?
               ORDER BY received_at, exchange_timestamp LIMIT ?""",
            (instrument_key, source_id, begin.isoformat(timespec="microseconds"),
             finish.isoformat(timespec="microseconds"), max_rows + 1),
        ).fetchall()
    if len(rows) > max_rows:
        raise OptionReplayError("replay_row_limit_exceeded")
    result = []
    previous = None
    for row in rows:
        payload = row["quote_json"]
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if digest != row["snapshot_sha256"]:
            raise OptionReplayError("snapshot_hash_mismatch")
        try:
            fields = json.loads(payload)
            for field in ("timestamp", "underlying_timestamp"):
                fields[field] = datetime.fromisoformat(fields[field])
            quote = OptionQuote(**fields)
            received = aware(datetime.fromisoformat(row["received_at"]), "received")
            stamp = aware(quote.timestamp, "exchange")
            underlying = aware(quote.underlying_timestamp, "underlying")
        except (ValueError, TypeError, KeyError) as exc:
            raise OptionReplayError("invalid_snapshot_payload") from exc
        if (quote.instrument_key != instrument_key or
                stamp.isoformat(timespec="microseconds") != row["exchange_timestamp"] or
                not begin <= received < finish or stamp > received or underlying > received):
            raise OptionReplayError("snapshot_metadata_or_causality_mismatch")
        if previous is not None and stamp <= previous:
            raise OptionReplayError("out_of_order_exchange_snapshot")
        previous = stamp
        result.append(ReplaySnapshot(quote, received, source_id, digest))
    return tuple(result)


def snapshot_as_of(
    snapshots: tuple[ReplaySnapshot, ...], *, decision_at: datetime,
    max_age_seconds: int = 2,
) -> ReplaySnapshot | None:
    """Select the newest available quote; never use a future receipt."""
    now = aware(decision_at, "decision_at")
    if type(max_age_seconds) is not int or max_age_seconds < 1:
        raise ValueError("invalid_max_age")
    if not snapshots:
        return None
    identity = (snapshots[0].quote.instrument_key, snapshots[0].source_id)
    last = None
    candidate = None
    for item in snapshots:
        if (item.quote.instrument_key, item.source_id) != identity:
            raise OptionReplayError("mixed_replay_identity")
        received = aware(item.received_at, "received_at")
        if last is not None and received < last:
            raise OptionReplayError("unordered_receipts")
        last = received
        if received <= now:
            candidate = item
    if candidate is None:
        return None
    for stamp in (candidate.quote.timestamp, candidate.quote.underlying_timestamp):
        age = now - aware(stamp, "quote_time")
        if not timedelta(0) <= age <= timedelta(seconds=max_age_seconds):
            return None
    if candidate.quote.trading_halted:
        return None
    return candidate
