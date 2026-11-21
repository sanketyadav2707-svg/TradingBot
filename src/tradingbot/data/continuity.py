"""Offline continuity guard for one-minute normalized candle feeds.

Gap detection never fills missing candles with fabricated prices. Any
unexpected timestamp or symbol requires feed recovery and explicit replay
from an authorized source before paper execution resumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from tradingbot.models import Bar


@dataclass(frozen=True, slots=True)
class ContinuityDecision:
    accepted: bool
    reason: str
    expected_timestamp: datetime | None


class ClosedBarContinuityGuard:
    """Strict within-session sequence gate; caller explicitly resets at session start."""

    def __init__(self, *, symbol: str, interval_seconds: int = 60) -> None:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol_required")
        if type(interval_seconds) is not int or interval_seconds < 1:
            raise ValueError("interval_seconds_must_be_positive")
        self.symbol = symbol.strip().upper()
        self.interval_seconds = interval_seconds
        self._last: datetime | None = None
        self._halt_reason: str | None = None

    @property
    def last_timestamp(self) -> datetime | None:
        return self._last

    @property
    def halted(self) -> bool:
        return self._halt_reason is not None

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason

    def inspect(self, bar: Bar) -> ContinuityDecision:
        if not isinstance(bar, Bar):
            raise TypeError("normalized_bar_required")
        expected = self._last + timedelta(seconds=self.interval_seconds) if self._last else None
        if self._halt_reason is not None:
            return ContinuityDecision(False, "continuity_guard_halted:" + self._halt_reason, expected)
        if bar.symbol.strip().upper() != self.symbol:
            self._halt_reason = "symbol_mismatch"
            return ContinuityDecision(False, self._halt_reason, expected)
        stamp = bar.timestamp.astimezone(timezone.utc)
        if expected is not None and stamp != expected:
            self._halt_reason = (
                "duplicate_or_out_of_order_bar" if stamp <= self._last else "missing_bar_gap"
            )
            return ContinuityDecision(False, self._halt_reason, expected)
        self._last = stamp
        return ContinuityDecision(True, "accepted", expected)

    def reset_for_new_session(self, *, flat: bool, reconciled: bool) -> None:
        if flat is not True or reconciled is not True:
            raise RuntimeError("session_reset_requires_flat_reconciled_account")
        self._last = None
        self._halt_reason = None
