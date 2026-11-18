"""Persistent paper-position exits and closed-bar trading-loop composition."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from tradingbot.accounting.engine import PaperAccountEngine
from tradingbot.execution.router import ExecutionMode, ExecutionRouter, OrderIntent
from tradingbot.models import Bar, Instrument, Side
from tradingbot.paper.broker import PaperFill
from tradingbot.runtime.strategy import ClosedBarStrategyRuntime, RuntimeState


@dataclass(frozen=True, slots=True)
class PositionExit:
    symbol: str
    reason: str
    reference_price: Decimal
    timestamp: datetime
    bars_held: int
    fills: tuple[PaperFill, ...]


class _PositionStateStore:
    """Persist stop/target and replay cursor beside the paper account database."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = str(database_path)
        with sqlite3.connect(self.path, timeout=10) as connection:
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_position_manager_state (
                    symbol TEXT PRIMARY KEY,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price TEXT NOT NULL,
                    entry_timestamp TEXT NOT NULL,
                    stop_ticks INTEGER NOT NULL,
                    target_ticks INTEGER NOT NULL,
                    max_holding_bars INTEGER NOT NULL,
                    bar_interval_seconds INTEGER NOT NULL,
                    last_bar_timestamp TEXT
                )
                """
            )

    def load(self, symbol: str) -> dict | None:
        with sqlite3.connect(self.path, timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM paper_position_manager_state WHERE symbol = ?",
                (symbol.upper(),),
            ).fetchone()
            return dict(row) if row is not None else None

    def save(self, state: dict) -> None:
        with sqlite3.connect(self.path, timeout=10) as connection:
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute(
                """
                INSERT INTO paper_position_manager_state(
                    symbol, side, quantity, entry_price, entry_timestamp,
                    stop_ticks, target_ticks, max_holding_bars,
                    bar_interval_seconds, last_bar_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    side=excluded.side,
                    quantity=excluded.quantity,
                    entry_price=excluded.entry_price,
                    entry_timestamp=excluded.entry_timestamp,
                    stop_ticks=excluded.stop_ticks,
                    target_ticks=excluded.target_ticks,
                    max_holding_bars=excluded.max_holding_bars,
                    bar_interval_seconds=excluded.bar_interval_seconds,
                    last_bar_timestamp=excluded.last_bar_timestamp
                """,
                (
                    state["symbol"], state["side"], state["quantity"],
                    state["entry_price"], state["entry_timestamp"],
                    state["stop_ticks"], state["target_ticks"],
                    state["max_holding_bars"], state["bar_interval_seconds"],
                    state["last_bar_timestamp"],
                ),
            )

    def delete(self, symbol: str) -> None:
        with sqlite3.connect(self.path, timeout=10) as connection:
            connection.execute(
                "DELETE FROM paper_position_manager_state WHERE symbol = ?",
                (symbol.upper(),),
            )


class PaperPositionManager:
    """Manage stop, target, time exit and restart recovery for one paper instrument.

    If both stop and target are touched in the same OHLC bar, stop-loss wins.
    State is persisted before the next event is accepted. A position without its
    matching management state is treated as unsafe and durably halts the account.
    """

    def __init__(
        self,
        engine: PaperAccountEngine,
        instrument: Instrument,
        *,
        stop_ticks: int,
        target_ticks: int,
        max_holding_bars: int,
        bar_interval_seconds: int = 60,
    ) -> None:
        if not isinstance(engine, PaperAccountEngine):
            raise TypeError("paper_account_engine_required")
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument_required")
        for name, value in (
            ("stop_ticks", stop_ticks),
            ("target_ticks", target_ticks),
            ("max_holding_bars", max_holding_bars),
            ("bar_interval_seconds", bar_interval_seconds),
        ):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name}_must_be_positive_integer")
        if max_holding_bars * bar_interval_seconds > 900:
            raise ValueError("paper_position_holding_limit_exceeds_15_minutes")
        self.engine = engine
        self.instrument = instrument
        self.stop_ticks = stop_ticks
        self.target_ticks = target_ticks
        self.max_holding_bars = max_holding_bars
        self.bar_interval_seconds = bar_interval_seconds
        self._state_store = _PositionStateStore(engine.store.path)
        self._state: dict | None = None
        self._halted = False
        self._reason = "ready"
        self._recover()

    @property
    def has_position(self) -> bool:
        return self._state is not None

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def reason(self) -> str:
        return self._reason

    def _position(self) -> dict | None:
        rows = [
            row for row in self.engine.store.list_positions()
            if str(row["symbol"]).upper() == self.instrument.symbol.upper()
        ]
        if len(rows) > 1:
            raise RuntimeError("paper_position_not_unique")
        return rows[0] if rows else None

    def _halt(self, reason: str) -> None:
        self._halted = True
        self._reason = reason
        self.engine.emergency_halt(reason)

    def _recover(self) -> None:
        position = self._position()
        saved = self._state_store.load(self.instrument.symbol)
        if position is None:
            if saved is not None:
                self._state_store.delete(self.instrument.symbol)
            return
        if saved is None:
            self._halt("position_manager_state_missing_after_restart")
            return
        entry_price = Decimal(str(position["average_entry_price"]))
        saved_entry_price = Decimal(str(saved["entry_price"]))
        opened_at = datetime.fromisoformat(
            str(position["opened_at"]).replace("Z", "+00:00")
        )
        saved_opened_at = datetime.fromisoformat(
            str(saved["entry_timestamp"]).replace("Z", "+00:00")
        )
        matches = (
            str(position["side"]) == str(saved["side"])
            and int(position["quantity"]) == int(saved["quantity"])
            and entry_price == saved_entry_price
            and opened_at.astimezone(timezone.utc) == saved_opened_at.astimezone(timezone.utc)
            and int(saved["stop_ticks"]) > 0
            and int(saved["target_ticks"]) > 0
            and int(saved["bar_interval_seconds"]) * int(saved["max_holding_bars"]) <= 900
        )
        if not matches:
            self._halt("position_manager_state_mismatch_after_restart")
            return
        self._state = saved
        self.stop_ticks = int(saved["stop_ticks"])
        self.target_ticks = int(saved["target_ticks"])
        self.max_holding_bars = int(saved["max_holding_bars"])
        self.bar_interval_seconds = int(saved["bar_interval_seconds"])

    def register_entry(self, fill: PaperFill) -> None:
        if self._halted:
            raise RuntimeError("position_manager_halted")
        if not isinstance(fill, PaperFill):
            raise TypeError("paper_fill_required")
        if fill.symbol.strip().upper() != self.instrument.symbol.upper():
            raise ValueError("entry_fill_instrument_mismatch")
        if fill.side not in (Side.LONG, Side.SHORT):
            raise ValueError("entry_fill_side_invalid")
        if fill.timestamp.tzinfo is None or fill.timestamp.utcoffset() is None:
            raise ValueError("entry_fill_timestamp_must_be_timezone_aware")
        if self.has_position:
            raise RuntimeError("position_already_managed")
        position = self._position()
        if position is None:
            raise RuntimeError("entry_fill_not_persisted_to_paper_account")
        if (
            position["side"] != ("LONG" if fill.side == Side.LONG else "SHORT")
            or int(position["quantity"]) != fill.quantity
            or Decimal(str(position["average_entry_price"])) != Decimal(str(fill.fill_price))
        ):
            self._halt("entry_fill_accounting_mismatch")
            raise RuntimeError("entry_fill_accounting_mismatch")
        state = {
            "symbol": self.instrument.symbol.upper(),
            "side": "LONG" if fill.side == Side.LONG else "SHORT",
            "quantity": int(fill.quantity),
            "entry_price": format(Decimal(str(fill.fill_price)), "f"),
            "entry_timestamp": fill.timestamp.astimezone(timezone.utc).isoformat(timespec="microseconds"),
            "stop_ticks": self.stop_ticks,
            "target_ticks": self.target_ticks,
            "max_holding_bars": self.max_holding_bars,
            "bar_interval_seconds": self.bar_interval_seconds,
            "last_bar_timestamp": None,
        }
        try:
            self._state_store.save(state)
        except Exception:
            self._halt("position_manager_state_persist_failed")
            raise
        self._state = state
        self._reason = "position_registered"

    def on_closed_bar(self, bar: Bar) -> PositionExit | None:
        if self._halted:
            raise RuntimeError("position_manager_halted")
        if not self.has_position:
            return None
        if not isinstance(bar, Bar) or bar.symbol.strip().upper() != self.instrument.symbol.upper():
            self._halt("position_bar_instrument_mismatch")
            raise ValueError("position_bar_instrument_mismatch")
        stamp = bar.timestamp.astimezone(timezone.utc)
        previous = self._state["last_bar_timestamp"]
        entry_stamp = datetime.fromisoformat(
            str(self._state["entry_timestamp"]).replace("Z", "+00:00")
        )
        if previous is not None:
            previous_stamp = datetime.fromisoformat(str(previous).replace("Z", "+00:00"))
            if stamp <= previous_stamp:
                self._halt("position_bar_duplicate_or_out_of_order")
                raise ValueError("position_bar_duplicate_or_out_of_order")
            expected_stamp = previous_stamp + timedelta(seconds=self.bar_interval_seconds)
        else:
            expected_stamp = entry_stamp.astimezone(timezone.utc)
        if stamp != expected_stamp.astimezone(timezone.utc):
            self._halt("position_bar_gap_detected")
            raise ValueError("position_bar_gap_detected")
        close_stamp = stamp + timedelta(seconds=self.bar_interval_seconds)
        if close_stamp <= entry_stamp:
            self._state["last_bar_timestamp"] = stamp.isoformat(timespec="microseconds")
            try:
                self._state_store.save(self._state)
            except Exception:
                self._halt("position_manager_state_persist_failed")
                raise
            return None

        bars_held = max(
            1,
            int((close_stamp - entry_stamp).total_seconds() // self.bar_interval_seconds),
        )
        entry = Decimal(str(self._state["entry_price"]))
        tick = Decimal(str(self.instrument.tick_size))
        stop_distance = tick * int(self._state["stop_ticks"])
        target_distance = tick * int(self._state["target_ticks"])
        high = Decimal(str(bar.high))
        low = Decimal(str(bar.low))
        close = Decimal(str(bar.close))
        side = self._state["side"]
        stop_price = entry - stop_distance if side == "LONG" else entry + stop_distance
        target_price = entry + target_distance if side == "LONG" else entry - target_distance
        stop_touched = low <= stop_price if side == "LONG" else high >= stop_price
        target_touched = high >= target_price if side == "LONG" else low <= target_price

        reason = None
        exit_price = None
        if stop_touched:
            reason, exit_price = "STOP_LOSS", stop_price
        elif target_touched:
            reason, exit_price = "TAKE_PROFIT", target_price
        elif bars_held >= int(self._state["max_holding_bars"]):
            reason, exit_price = "TIME_EXIT", close

        if reason is None:
            self._state["last_bar_timestamp"] = stamp.isoformat(timespec="microseconds")
            try:
                self._state_store.save(self._state)
            except Exception:
                self._halt("position_manager_state_persist_failed")
                raise
            self._reason = "position_open"
            return None

        try:
            fills = self.engine.close_position(
                self.instrument,
                reference_price=float(exit_price),
                timestamp=close_stamp,
            )
        except Exception:
            self._halt("position_exit_execution_failed")
            raise
        self._state_store.delete(self.instrument.symbol)
        self._state = None
        self._reason = reason.lower()
        return PositionExit(
            symbol=self.instrument.symbol,
            reason=reason,
            reference_price=exit_price,
            timestamp=close_stamp,
            bars_held=bars_held,
            fills=fills,
        )

    def force_flatten(
        self,
        *,
        reference_price: float,
        timestamp: datetime,
        reason: str = "SESSION_END",
    ) -> PositionExit | None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("position_exit_reason_required")
        position = self._position()
        if position is None:
            self._state_store.delete(self.instrument.symbol)
            self._state = None
            return None
        try:
            fills = self.engine.close_position(
                self.instrument, reference_price=reference_price, timestamp=timestamp
            )
        except Exception:
            self._halt("operator_position_flatten_failed")
            raise
        try:
            self._state_store.delete(self.instrument.symbol)
        except Exception:
            self._halt("position_manager_state_cleanup_failed")
            raise
        self._state = None
        self._reason = reason.strip().upper()
        return PositionExit(
            symbol=self.instrument.symbol,
            reason=reason.strip().upper(),
            reference_price=Decimal(str(reference_price)),
            timestamp=timestamp,
            bars_held=0,
            fills=fills,
        )

    def halt(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("position_manager_halt_reason_required")
        self._halt(reason.strip())


class PaperTradingLoop:
    """Drive next-bar-open paper entries and managed exits from one closed-bar stream.

    A signal produced at bar close is queued. It can only execute at the next
    contiguous bar's open, never at the signal bar's close. While a position is
    open, strategy history is still updated but new entries are suppressed.
    """

    def __init__(
        self,
        *,
        strategy_runtime: ClosedBarStrategyRuntime,
        position_manager: PaperPositionManager,
        router: ExecutionRouter,
    ) -> None:
        if not isinstance(strategy_runtime, ClosedBarStrategyRuntime):
            raise TypeError("closed_bar_strategy_runtime_required")
        if not isinstance(position_manager, PaperPositionManager):
            raise TypeError("paper_position_manager_required")
        if not isinstance(router, ExecutionRouter) or router.mode != ExecutionMode.PAPER:
            raise TypeError("paper_execution_router_required")
        if router.risk_guard is None:
            raise ValueError("paper_loop_requires_risk_guard")
        self.strategy_runtime = strategy_runtime
        self.position_manager = position_manager
        self.router = router
        self._pending_signal = None
        # The loop owns dispatch so it can defer execution until the next bar open.
        self.strategy_runtime.on_signal = self._queue_signal

    @property
    def pending_signal(self):
        return self._pending_signal

    def _queue_signal(self, signal) -> None:
        if self._pending_signal is not None:
            raise RuntimeError("previous_signal_not_consumed")
        self._pending_signal = signal

    def cancel_pending_signal(self, reason: str = "session_end") -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("pending_signal_cancel_reason_required")
        self._pending_signal = None

    def process_closed_bar(self, bar: Bar, *, received_at: datetime):
        if self.position_manager.halted or self.strategy_runtime.state != RuntimeState.RUNNING:
            return None

        if self.position_manager.has_position:
            self.strategy_runtime.process_closed_bar(
                bar, received_at=received_at, allow_signal=False
            )
            if self.strategy_runtime.state != RuntimeState.RUNNING:
                self.position_manager.halt(self.strategy_runtime.reason)
                return None
            return self.position_manager.on_closed_bar(bar)

        if self._pending_signal is None:
            result = self.strategy_runtime.process_closed_bar(
                bar, received_at=received_at, allow_signal=True
            )
            if self.strategy_runtime.state != RuntimeState.RUNNING:
                self.position_manager.halt(self.strategy_runtime.reason)
                return None
            return result

        expected_open = self._pending_signal.timestamp.astimezone(timezone.utc)
        actual_open = bar.timestamp.astimezone(timezone.utc)
        if actual_open != expected_open:
            # A missing candle invalidates the queued entry. Reprocess this bar
            # as a fresh decision point, without executing a stale signal.
            self._pending_signal = None
            result = self.strategy_runtime.process_closed_bar(
                bar, received_at=received_at, allow_signal=True
            )
            if self.strategy_runtime.state != RuntimeState.RUNNING:
                self.position_manager.halt(self.strategy_runtime.reason)
                return None
            return result

        signal = self._pending_signal
        self._pending_signal = None
        self.strategy_runtime.process_closed_bar(
            bar, received_at=received_at, allow_signal=False
        )
        if self.strategy_runtime.state != RuntimeState.RUNNING:
            self.position_manager.halt(self.strategy_runtime.reason)
            return None

        try:
            fill = self.router.submit_entry(
                OrderIntent(
                    instrument=self.position_manager.instrument,
                    side=signal.side,
                    stop_ticks=self.position_manager.stop_ticks,
                    reference_price=bar.open,
                    timestamp=bar.timestamp,
                    idempotency_key=signal.signal_id,
                )
            )
            self.position_manager.register_entry(fill)
            exit_event = self.position_manager.on_closed_bar(bar)
            return exit_event if exit_event is not None else fill
        except Exception:
            self.position_manager.halt("paper_entry_or_position_registration_failed")
            self.strategy_runtime.halt(reason="paper_entry_or_position_registration_failed")
            raise

    def force_flatten(
        self,
        *,
        reference_price: float,
        timestamp: datetime,
        reason: str = "SESSION_END",
    ) -> PositionExit | None:
        self.cancel_pending_signal("forced_flatten")
        return self.position_manager.force_flatten(
            reference_price=reference_price,
            timestamp=timestamp,
            reason=reason,
        )
