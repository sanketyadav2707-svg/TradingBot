"""Fail-closed closed-bar market-data gate and incremental strategy runtime.

The strategy callback only receives the current completed bar and its completed
history. It cannot be handed future bars by this runtime. Order execution remains
an injected callback and must route through ExecutionRouter/RiskGuard.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Callable, Sequence

from tradingbot.models import Bar, Signal, Side


class RuntimeState(str, Enum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class ValidatedSignal:
    signal_id: str
    symbol: str
    timestamp: datetime
    side: Side
    reason: str


@dataclass(frozen=True, slots=True)
class MarketDataDecision:
    accepted: bool
    reason: str


class MarketDataGate:
    """Validate symbol, freshness, future timestamps and strict event ordering."""

    def __init__(
        self,
        *,
        symbol: str,
        max_age_seconds: int = 60,
        bar_interval_seconds: int = 60,
        session_check: Callable[[Bar], bool] | None = None,
    ) -> None:
        if not symbol.strip():
            raise ValueError("market_data_symbol_required")
        if type(max_age_seconds) is not int or max_age_seconds < 1:
            raise ValueError("max_age_seconds_must_be_positive_integer")
        if type(bar_interval_seconds) is not int or bar_interval_seconds < 1:
            raise ValueError("bar_interval_seconds_must_be_positive_integer")
        self.symbol = symbol.strip().upper()
        self.max_age_seconds = max_age_seconds
        self.bar_interval_seconds = bar_interval_seconds
        self.session_check = session_check
        self._last_timestamp: datetime | None = None
        self._lock = RLock()

    @property
    def last_timestamp(self) -> datetime | None:
        with self._lock:
            return self._last_timestamp

    def validate(self, bar: Bar, *, received_at: datetime) -> MarketDataDecision:
        with self._lock:
            if not isinstance(bar, Bar):
                return MarketDataDecision(False, "bar_type_invalid")
            if received_at.tzinfo is None or received_at.utcoffset() is None:
                return MarketDataDecision(False, "receive_timestamp_must_be_timezone_aware")
            if bar.symbol.strip().upper() != self.symbol:
                return MarketDataDecision(False, "market_data_symbol_mismatch")
            observed = bar.timestamp.astimezone(timezone.utc)
            received = received_at.astimezone(timezone.utc)
            bar_close = observed + timedelta(seconds=self.bar_interval_seconds)
            age = (received - bar_close).total_seconds()
            if age < 0:
                return MarketDataDecision(False, "future_dated_market_bar")
            if age > self.max_age_seconds:
                return MarketDataDecision(False, "stale_market_bar")
            if self._last_timestamp is not None and observed <= self._last_timestamp:
                return MarketDataDecision(False, "duplicate_or_out_of_order_market_bar")
            if self.session_check is not None:
                try:
                    if self.session_check(bar) is not True:
                        return MarketDataDecision(False, "market_bar_outside_verified_session")
                except Exception:
                    return MarketDataDecision(False, "market_session_check_failed")
            self._last_timestamp = observed
            return MarketDataDecision(True, "accepted")


class SignalValidator:
    """Validate strategy signals and produce deterministic, duplicate-safe IDs."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = RLock()

    def validate(self, bar: Bar, signal: Signal) -> tuple[ValidatedSignal | None, str]:
        if not isinstance(signal, Signal):
            return None, "signal_type_invalid"
        if signal.side not in (Side.LONG, Side.SHORT):
            return None, "signal_side_invalid"
        if not isinstance(signal.reason, str) or not signal.reason.strip():
            return None, "signal_reason_required"
        stamp = bar.timestamp.astimezone(timezone.utc).isoformat(timespec="microseconds")
        material = "|".join((bar.symbol.strip().upper(), stamp, str(int(signal.side)), signal.reason.strip()))
        signal_id = hashlib.sha256(material.encode("utf-8")).hexdigest()
        with self._lock:
            if signal_id in self._seen:
                return None, "duplicate_signal"
            self._seen.add(signal_id)
        return ValidatedSignal(
            signal_id=signal_id,
            symbol=bar.symbol.strip().upper(),
            timestamp=bar.timestamp,
            side=signal.side,
            reason=signal.reason.strip(),
        ), "accepted"


class ClosedBarStrategyRuntime:
    """Process one completed bar at a time and fail closed on any callback error.

    `strategy_on_bar` receives only the current bar and a tuple ending at that
    bar. `on_signal` is expected to create an OrderIntent and submit it through
    the risk/compliance-gated ExecutionRouter, never directly to a broker.
    """

    def __init__(
        self,
        *,
        market_data_gate: MarketDataGate,
        strategy_on_bar: Callable[[Bar, Sequence[Bar]], Signal | None],
        on_signal: Callable[[ValidatedSignal], None],
        max_history_bars: int = 20_000,
        signal_validator: SignalValidator | None = None,
    ) -> None:
        if type(max_history_bars) is not int or max_history_bars < 2:
            raise ValueError("max_history_bars_must_be_at_least_two")
        self.market_data_gate = market_data_gate
        self.strategy_on_bar = strategy_on_bar
        self.on_signal = on_signal
        self.max_history_bars = max_history_bars
        self.signal_validator = signal_validator or SignalValidator()
        self._history: list[Bar] = []
        self._state = RuntimeState.RUNNING
        self._reason = "ready"
        self._lock = RLock()

    @property
    def state(self) -> RuntimeState:
        with self._lock:
            return self._state

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def history(self) -> tuple[Bar, ...]:
        with self._lock:
            return tuple(self._history)

    def process_closed_bar(self, bar: Bar, *, received_at: datetime) -> ValidatedSignal | None:
        with self._lock:
            if self._state != RuntimeState.RUNNING:
                return None
            decision = self.market_data_gate.validate(bar, received_at=received_at)
            if not decision.accepted:
                self._state = RuntimeState.DEGRADED
                self._reason = decision.reason
                return None
            self._history.append(bar)
            if len(self._history) > self.max_history_bars:
                del self._history[: len(self._history) - self.max_history_bars]
            visible_history = tuple(self._history)
            try:
                signal = self.strategy_on_bar(bar, visible_history)
                if signal is None:
                    return None
                validated, reason = self.signal_validator.validate(bar, signal)
                if validated is None:
                    self._reason = reason
                    return None
                self.on_signal(validated)
                self._reason = "signal_dispatched"
                return validated
            except Exception:
                self._state = RuntimeState.DEGRADED
                self._reason = "strategy_or_signal_handler_failed"
                return None

    def halt(self, *, reason: str) -> None:
        with self._lock:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("halt_reason_required")
            self._state = RuntimeState.HALTED
            self._reason = reason.strip()

