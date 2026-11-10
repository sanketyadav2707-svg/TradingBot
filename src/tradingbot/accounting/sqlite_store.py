"""Durable FIFO paper-account ledger backed by SQLite.

This module never submits orders or connects to a broker. It records fills that
have already been produced by the local PaperBroker and derives positions,
closed trades and account snapshots from that immutable fill history.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, Mapping

from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperFill

_CENT = Decimal("0.01")


class DuplicateFillError(ValueError):
    """An order/fill identifier was reused with different execution data."""


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite decimal")
    return result


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _money(value: Decimal) -> str:
    return format(value.quantize(_CENT), "f")


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


class PaperAccountStore:
    """Transactional, restart-safe accounting for one simulated futures account.

    Fill identifiers are idempotency keys. Opposing fills close existing lots FIFO;
    any excess quantity opens a reversed position. All cash/P&L arithmetic uses
    Decimal values serialized as text in SQLite.
    """

    def __init__(self, database_path: str | Path, starting_balance_usd: float | Decimal) -> None:
        self.path = Path(database_path).expanduser().resolve()
        if str(database_path) == ":memory:":
            raise ValueError("Use a temporary SQLite file for tests; in-memory databases are unsupported")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        starting_balance = _decimal(starting_balance_usd, "starting_balance_usd")
        if starting_balance <= 0:
            raise ValueError("starting_balance_usd must be positive")
        self._initialize(starting_balance)

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

    def _initialize(self, starting_balance: Decimal) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS account_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fills (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side INTEGER NOT NULL CHECK (side IN (-1, 1)),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    requested_price TEXT NOT NULL,
                    fill_price TEXT NOT NULL,
                    commission_usd TEXT NOT NULL,
                    tick_size TEXT NOT NULL,
                    tick_value_usd TEXT NOT NULL,
                    point_value_usd TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS open_lots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side INTEGER NOT NULL CHECK (side IN (-1, 1)),
                    quantity_open INTEGER NOT NULL CHECK (quantity_open > 0),
                    entry_price TEXT NOT NULL,
                    entry_commission_remaining TEXT NOT NULL,
                    tick_size TEXT NOT NULL,
                    tick_value_usd TEXT NOT NULL,
                    point_value_usd TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    opening_fill_id TEXT NOT NULL REFERENCES fills(order_id)
                );
                CREATE INDEX IF NOT EXISTS idx_open_lots_symbol_id
                    ON open_lots(symbol, id);
                CREATE TABLE IF NOT EXISTS closed_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side INTEGER NOT NULL CHECK (side IN (-1, 1)),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    entry_price TEXT NOT NULL,
                    exit_price TEXT NOT NULL,
                    gross_pnl_usd TEXT NOT NULL,
                    entry_commission_usd TEXT NOT NULL,
                    exit_commission_usd TEXT NOT NULL,
                    net_pnl_usd TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    opening_fill_id TEXT NOT NULL REFERENCES fills(order_id),
                    closing_fill_id TEXT NOT NULL REFERENCES fills(order_id)
                );
                CREATE INDEX IF NOT EXISTS idx_closed_trades_exit_time
                    ON closed_trades(exit_time, id);
                CREATE TABLE IF NOT EXISTS marks (
                    symbol TEXT PRIMARY KEY,
                    price TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    balance_usd TEXT NOT NULL,
                    realized_gross_pnl_usd TEXT NOT NULL,
                    commissions_usd TEXT NOT NULL,
                    unrealized_pnl_usd TEXT,
                    equity_usd TEXT,
                    reference_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_equity_snapshots_time
                    ON equity_snapshots(timestamp, id);
                CREATE TABLE IF NOT EXISTS account_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    reference_id TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_account_events_time
                    ON account_events(timestamp, id);
                """
            )
            # Upgrade pre-specification databases only when no open lots need
            # contract metadata that the older schema never stored.
            for table in ("fills", "open_lots"):
                columns = {
                    row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                }
                missing = [name for name in ("tick_size", "tick_value_usd") if name not in columns]
                if missing:
                    open_lots_count = connection.execute(
                        "SELECT COUNT(*) AS n FROM open_lots"
                    ).fetchone()["n"]
                    if open_lots_count:
                        raise RuntimeError(
                            "paper account database lacks full contract specifications for open lots; "
                            "reconcile/close positions before upgrading the ledger"
                        )
                    for name in missing:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} TEXT")

            connection.execute(
                "INSERT OR IGNORE INTO account_meta(key, value) VALUES ('starting_balance_usd', ?)",
                (_number(starting_balance),),
            )
            stored_balance = Decimal(connection.execute(
                "SELECT value FROM account_meta WHERE key = 'starting_balance_usd'"
            ).fetchone()["value"])
            if stored_balance != starting_balance:
                raise ValueError(
                    "starting_balance_usd does not match the existing persistent paper account; "
                    "refusing to silently reset or reinterpret account history"
                )
            snapshots = connection.execute(
                "SELECT COUNT(*) AS n FROM equity_snapshots"
            ).fetchone()["n"]
            if snapshots == 0:
                created_at = _timestamp(datetime.now(timezone.utc))
                connection.execute(
                    """INSERT INTO account_events(
                        timestamp, event_type, symbol, reference_id, payload_json
                    ) VALUES (?, 'ACCOUNT_INITIALIZED', NULL, NULL, ?)""",
                    (
                        created_at,
                        json.dumps({"starting_balance_usd": _number(starting_balance)}, sort_keys=True),
                    ),
                )
                self._write_snapshot(connection, created_at, "ACCOUNT_INITIALIZED", None)

    @property
    def starting_balance_usd(self) -> Decimal:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM account_meta WHERE key = 'starting_balance_usd'"
            ).fetchone()
        if row is None:
            raise RuntimeError("Paper account starting balance is missing")
        return Decimal(row["value"])

    def validate_instrument(self, instrument: Instrument) -> None:
        """Reject changed contract specifications while any FIFO lot remains open."""
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        symbol = instrument.symbol.strip().upper()
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT tick_size, tick_value_usd, point_value_usd FROM open_lots WHERE symbol = ?",
                (symbol,),
            ).fetchall()
        expected = (
            Decimal(str(instrument.tick_size)),
            Decimal(str(instrument.tick_value_usd)),
            Decimal(str(instrument.point_value_usd)),
        )
        if any(
            row["tick_size"] is None
            or row["tick_value_usd"] is None
            or row["point_value_usd"] is None
            or (
                Decimal(row["tick_size"]),
                Decimal(row["tick_value_usd"]),
                Decimal(row["point_value_usd"]),
            ) != expected
            for row in rows
        ):
            raise ValueError(
                "contract tick/point specification changed or is unknown while a position is open"
            )

    def record_fill(self, fill: PaperFill, instrument: Instrument) -> bool:
        """Persist a PaperBroker fill and update FIFO lots atomically.

        Returns False for an exact duplicate. Reusing an order_id with altered
        execution details raises DuplicateFillError and changes nothing.
        """
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(fill, PaperFill):
            raise TypeError("fill must be a PaperFill")
        symbol = fill.symbol.strip().upper()
        if not symbol or symbol != instrument.symbol.strip().upper():
            raise ValueError("Fill symbol must match the supplied instrument")
        if not isinstance(fill.side, Side) or fill.side not in (Side.LONG, Side.SHORT):
            raise ValueError("Fill side must be LONG or SHORT")
        if type(fill.quantity) is not int or fill.quantity < 1:
            raise ValueError("Fill quantity must be a positive integer")
        if not isinstance(fill.order_id, str) or not fill.order_id.strip():
            raise ValueError("Fill order_id cannot be empty")

        requested = _decimal(fill.requested_price, "requested_price")
        price = _decimal(fill.fill_price, "fill_price")
        commission = _decimal(fill.commission_usd, "commission_usd")
        tick_size = _decimal(instrument.tick_size, "tick_size")
        tick_value = _decimal(instrument.tick_value_usd, "tick_value_usd")
        point_value = _decimal(instrument.point_value_usd, "point_value_usd")
        if commission < 0 or tick_size <= 0 or tick_value <= 0 or point_value <= 0:
            raise ValueError("Commission must be non-negative and point value positive")
        timestamp = _timestamp(fill.timestamp)
        side = int(fill.side)
        normalized_id = fill.order_id.strip()

        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM fills WHERE order_id = ?", (normalized_id,)
            ).fetchone()
            candidate = (
                symbol, side, fill.quantity, _number(requested), _number(price),
                _number(commission), _number(tick_size), _number(tick_value),
                _number(point_value), timestamp,
            )
            if existing is not None:
                actual = (
                    existing["symbol"], existing["side"], existing["quantity"],
                    existing["requested_price"], existing["fill_price"],
                    existing["commission_usd"], existing["tick_size"],
                    existing["tick_value_usd"], existing["point_value_usd"],
                    existing["timestamp"],
                )
                if actual != candidate:
                    raise DuplicateFillError("order_id_already_exists_with_different_fill_data")
                return False

            connection.execute(
                """INSERT INTO fills(
                    order_id, symbol, side, quantity, requested_price, fill_price,
                    commission_usd, tick_size, tick_value_usd, point_value_usd, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (normalized_id, *candidate),
            )
            remaining = fill.quantity
            fee_per_contract = commission / Decimal(fill.quantity)
            open_lots = connection.execute(
                "SELECT * FROM open_lots WHERE symbol = ? ORDER BY id", (symbol,)
            ).fetchall()
            if open_lots and any(
                Decimal(row["tick_size"]) != tick_size
                or Decimal(row["tick_value_usd"]) != tick_value
                or Decimal(row["point_value_usd"]) != point_value
                for row in open_lots
            ):
                raise ValueError(
                    "contract tick/point specification changed while this symbol has an open position; "
                    "close the existing position before changing contract specifications"
                )
            if open_lots and any(row["side"] != open_lots[0]["side"] for row in open_lots):
                raise RuntimeError("Position ledger invariant violated: mixed sides for one symbol")

            if not open_lots or open_lots[0]["side"] == side:
                connection.execute(
                    """INSERT INTO open_lots(
                        symbol, side, quantity_open, entry_price, entry_commission_remaining,
                        tick_size, tick_value_usd, point_value_usd, opened_at, opening_fill_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (symbol, side, remaining, _number(price), _number(commission),
                     _number(tick_size), _number(tick_value), _number(point_value), timestamp, normalized_id),
                )
                remaining = 0
            else:
                closed_quantity = 0
                for lot in open_lots:
                    if remaining == 0:
                        break
                    lot_quantity = int(lot["quantity_open"])
                    quantity = min(remaining, lot_quantity)
                    entry_commission_left = Decimal(lot["entry_commission_remaining"])
                    entry_commission = (
                        entry_commission_left
                        if quantity == lot_quantity
                        else entry_commission_left * Decimal(quantity) / Decimal(lot_quantity)
                    )
                    exit_commission = fee_per_contract * Decimal(quantity)
                    entry_price = Decimal(lot["entry_price"])
                    gross = (
                        (price - entry_price)
                        * Decimal(str(lot["point_value_usd"]))
                        * Decimal(int(lot["side"]))
                        * Decimal(quantity)
                    )
                    net = gross - entry_commission - exit_commission
                    connection.execute(
                        """INSERT INTO closed_trades(
                            symbol, side, quantity, entry_price, exit_price, gross_pnl_usd,
                            entry_commission_usd, exit_commission_usd, net_pnl_usd,
                            entry_time, exit_time, opening_fill_id, closing_fill_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            symbol, lot["side"], quantity, lot["entry_price"], _number(price),
                            _number(gross), _number(entry_commission), _number(exit_commission),
                            _number(net), lot["opened_at"], timestamp,
                            lot["opening_fill_id"], normalized_id,
                        ),
                    )
                    new_quantity = lot_quantity - quantity
                    if new_quantity == 0:
                        connection.execute("DELETE FROM open_lots WHERE id = ?", (lot["id"],))
                    else:
                        connection.execute(
                            """UPDATE open_lots
                               SET quantity_open = ?, entry_commission_remaining = ?
                               WHERE id = ?""",
                            (new_quantity, _number(entry_commission_left - entry_commission), lot["id"]),
                        )
                    connection.execute(
                        """INSERT INTO account_events(
                            timestamp, event_type, symbol, reference_id, payload_json
                        ) VALUES (?, 'TRADE_CLOSED', ?, ?, ?)""",
                        (
                            timestamp, symbol, normalized_id,
                            json.dumps({
                                "quantity": quantity, "gross_pnl_usd": _number(gross),
                                "entry_commission_usd": _number(entry_commission),
                                "exit_commission_usd": _number(exit_commission),
                                "net_pnl_usd": _number(net),
                            }, sort_keys=True),
                        ),
                    )
                    remaining -= quantity
                    closed_quantity += quantity

                if remaining > 0:
                    remaining_commission = commission - fee_per_contract * Decimal(closed_quantity)
                    connection.execute(
                        """INSERT INTO open_lots(
                            symbol, side, quantity_open, entry_price, entry_commission_remaining,
                            tick_size, tick_value_usd, point_value_usd, opened_at, opening_fill_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            symbol, side, remaining, _number(price), _number(remaining_commission),
                            _number(tick_size), _number(tick_value), _number(point_value), timestamp, normalized_id,
                        ),
                    )
                    remaining = 0

            connection.execute(
                """INSERT INTO account_events(
                    timestamp, event_type, symbol, reference_id, payload_json
                ) VALUES (?, 'FILL_RECORDED', ?, ?, ?)""",
                (
                    timestamp, symbol, normalized_id,
                    json.dumps({
                        "side": side, "quantity": fill.quantity,
                        "requested_price": _number(requested), "fill_price": _number(price),
                        "commission_usd": _number(commission),
                    }, sort_keys=True),
                ),
            )
            self._write_snapshot(connection, timestamp, "FILL", normalized_id)
        return True

    def mark_to_market(self, prices: Mapping[str, float | Decimal], timestamp: datetime) -> None:
        """Persist externally observed marks. This method does not fetch market data."""
        mark_time = _timestamp(timestamp)
        normalized: dict[str, Decimal] = {}
        for symbol, value in prices.items():
            key = symbol.strip().upper()
            if not key:
                raise ValueError("Mark symbol cannot be empty")
            normalized[key] = _decimal(value, f"mark[{key}]")
        if not normalized:
            raise ValueError("At least one mark price is required")

        with self._transaction() as connection:
            for symbol, price in normalized.items():
                previous = connection.execute(
                    "SELECT timestamp FROM marks WHERE symbol = ?", (symbol,)
                ).fetchone()
                if previous is not None and mark_time < previous["timestamp"]:
                    raise ValueError(f"Mark timestamp for {symbol} cannot move backwards")
                connection.execute(
                    """INSERT INTO marks(symbol, price, timestamp) VALUES (?, ?, ?)
                       ON CONFLICT(symbol) DO UPDATE SET price = excluded.price,
                       timestamp = excluded.timestamp""",
                    (symbol, _number(price), mark_time),
                )
                connection.execute(
                    """INSERT INTO account_events(
                        timestamp, event_type, symbol, reference_id, payload_json
                    ) VALUES (?, 'MARK_UPDATED', ?, NULL, ?)""",
                    (mark_time, symbol, json.dumps({"price": _number(price)}, sort_keys=True)),
                )
            self._write_snapshot(connection, mark_time, "MARK", None)

    def _summary(self, connection: sqlite3.Connection) -> dict[str, Any]:
        start = Decimal(connection.execute(
            "SELECT value FROM account_meta WHERE key = 'starting_balance_usd'"
        ).fetchone()["value"])
        # Re-sum decimal text in Python; SQLite REAL aggregation is not used for money.
        gross = sum(
            (Decimal(row["gross_pnl_usd"]) for row in connection.execute(
                "SELECT gross_pnl_usd FROM closed_trades"
            ).fetchall()),
            Decimal("0"),
        )
        commissions = sum(
            (Decimal(row["commission_usd"]) for row in connection.execute(
                "SELECT commission_usd FROM fills"
            ).fetchall()),
            Decimal("0"),
        )
        realized_net = sum(
            (Decimal(row["net_pnl_usd"]) for row in connection.execute(
                "SELECT net_pnl_usd FROM closed_trades"
            ).fetchall()),
            Decimal("0"),
        )
        balance = start + gross - commissions
        lots = connection.execute("SELECT * FROM open_lots ORDER BY symbol, id").fetchall()
        open_symbols = {row["symbol"] for row in lots}
        marks = {
            row["symbol"]: (Decimal(row["price"]), row["timestamp"])
            for row in connection.execute("SELECT * FROM marks").fetchall()
        }
        unrealized: Decimal | None = Decimal("0")
        if any(symbol not in marks for symbol in open_symbols):
            unrealized = None
        else:
            for lot in lots:
                mark = marks[lot["symbol"]][0]
                unrealized += (
                    (mark - Decimal(lot["entry_price"]))
                    * Decimal(lot["point_value_usd"])
                    * Decimal(int(lot["side"]))
                    * Decimal(int(lot["quantity_open"]))
                )
        equity = balance + unrealized if unrealized is not None else None

        peak = start
        max_drawdown = Decimal("0")
        for row in connection.execute(
            "SELECT equity_usd FROM equity_snapshots WHERE equity_usd IS NOT NULL ORDER BY id"
        ).fetchall():
            value = Decimal(row["equity_usd"])
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, peak - value)

        return {
            "starting_balance_usd": _number(start),
            "balance_usd": _number(balance),
            "realized_gross_pnl_usd": _number(gross),
            "realized_net_pnl_usd": _number(realized_net),
            "total_commissions_usd": _number(commissions),
            "unrealized_pnl_usd": _number(unrealized) if unrealized is not None else None,
            "equity_usd": _number(equity) if equity is not None else None,
            "net_pnl_usd": _number(equity - start) if equity is not None else None,
            "max_drawdown_usd": _number(max_drawdown),
            "open_positions": len({row["symbol"] for row in lots}),
            "open_contracts": sum(int(row["quantity_open"]) for row in lots),
            "fills_count": connection.execute("SELECT COUNT(*) AS n FROM fills").fetchone()["n"],
            "closed_trades_count": connection.execute("SELECT COUNT(*) AS n FROM closed_trades").fetchone()["n"],
            "as_of": max(
                [row["timestamp"] for row in connection.execute(
                    "SELECT timestamp FROM equity_snapshots ORDER BY id DESC LIMIT 1"
                ).fetchall()],
                default=None,
            ),
        }

    def _write_snapshot(
        self, connection: sqlite3.Connection, timestamp: str, source: str, reference_id: str | None
    ) -> None:
        summary = self._summary(connection)
        connection.execute(
            """INSERT INTO equity_snapshots(
                timestamp, source, balance_usd, realized_gross_pnl_usd,
                commissions_usd, unrealized_pnl_usd, equity_usd, reference_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp, source, summary["balance_usd"], summary["realized_gross_pnl_usd"],
                summary["total_commissions_usd"], summary["unrealized_pnl_usd"],
                summary["equity_usd"], reference_id,
            ),
        )

    def get_summary(self) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            return self._summary(connection)

    def count_records(self, table: str) -> int:
        allowed = {
            "fills": "fills",
            "closed_trades": "closed_trades",
            "account_events": "account_events",
        }
        selected = allowed.get(table)
        if selected is None:
            raise ValueError("Unsupported account record table")
        with self._lock, self._connection() as connection:
            return int(connection.execute(
                f"SELECT COUNT(*) AS n FROM {selected}"
            ).fetchone()["n"])

    def list_positions(self) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            lots = connection.execute("SELECT * FROM open_lots ORDER BY symbol, id").fetchall()
            marks = {
                row["symbol"]: (Decimal(row["price"]), row["timestamp"])
                for row in connection.execute("SELECT * FROM marks").fetchall()
            }
            grouped: dict[str, list[sqlite3.Row]] = {}
            for lot in lots:
                grouped.setdefault(lot["symbol"], []).append(lot)
            result: list[dict[str, Any]] = []
            for symbol, items in grouped.items():
                side = int(items[0]["side"])
                quantity = sum(int(item["quantity_open"]) for item in items)
                if any(int(item["side"]) != side for item in items):
                    raise RuntimeError("Position ledger invariant violated: mixed sides for one symbol")
                weighted = sum(
                    (Decimal(item["entry_price"]) * int(item["quantity_open"]) for item in items),
                    Decimal("0"),
                ) / Decimal(quantity)
                if symbol in marks:
                    mark, mark_time = marks[symbol]
                    unrealized = sum(
                        (
                            (mark - Decimal(item["entry_price"]))
                            * Decimal(item["point_value_usd"])
                            * Decimal(side)
                            * Decimal(int(item["quantity_open"]))
                        )
                        for item in items
                    )
                    mark_value: str | None = _number(mark)
                    mark_timestamp: str | None = mark_time
                    unrealized_value: str | None = _money(unrealized)
                else:
                    mark_value = None
                    mark_timestamp = None
                    unrealized_value = None
                result.append({
                    "symbol": symbol,
                    "side": "LONG" if side > 0 else "SHORT",
                    "quantity": quantity,
                    "average_entry_price": _number(weighted),
                    "mark_price": mark_value,
                    "unrealized_pnl_usd": unrealized_value,
                    "opened_at": min(item["opened_at"] for item in items),
                    "mark_timestamp": mark_timestamp,
                })
            return result

    def list_trades(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM closed_trades ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            return [{
                "id": row["id"], "symbol": row["symbol"],
                "side": "LONG" if row["side"] > 0 else "SHORT",
                "quantity": row["quantity"], "entry_price": row["entry_price"],
                "exit_price": row["exit_price"], "gross_pnl_usd": _money(Decimal(row["gross_pnl_usd"])),
                "entry_commission_usd": _money(Decimal(row["entry_commission_usd"])),
                "exit_commission_usd": _money(Decimal(row["exit_commission_usd"])),
                "net_pnl_usd": _money(Decimal(row["net_pnl_usd"])),
                "entry_time": row["entry_time"], "exit_time": row["exit_time"],
                "opening_fill_id": row["opening_fill_id"], "closing_fill_id": row["closing_fill_id"],
            } for row in rows]

    def list_fills(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM fills ORDER BY timestamp DESC, rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [{
                "order_id": row["order_id"], "symbol": row["symbol"],
                "side": "LONG" if row["side"] > 0 else "SHORT",
                "quantity": row["quantity"], "requested_price": row["requested_price"],
                "fill_price": row["fill_price"],
                "commission_usd": _money(Decimal(row["commission_usd"])),
                "timestamp": row["timestamp"],
            } for row in rows]

    def list_equity(self, limit: int = 500) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 5000:
            raise ValueError("limit must be an integer between 1 and 5000")
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """SELECT timestamp, equity_usd FROM equity_snapshots
                   WHERE equity_usd IS NOT NULL ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [{"timestamp": row["timestamp"], "equity_usd": row["equity_usd"]} for row in reversed(rows)]

    def list_events(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM account_events ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            return [{
                "id": row["id"], "timestamp": row["timestamp"],
                "event_type": row["event_type"], "symbol": row["symbol"],
                "reference_id": row["reference_id"], "payload": json.loads(row["payload_json"]),
            } for row in rows]

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a non-negative integer")
