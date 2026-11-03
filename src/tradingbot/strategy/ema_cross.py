"""Simple EMA crossover used only to verify the research pipeline.

This is not presented as a profitable or live-ready strategy.
"""

from __future__ import annotations

from tradingbot.models import Bar, Side, Signal


def _ema(values: list[float], period: int) -> list[float]:
    if period < 1:
        raise ValueError("EMA period must be at least 1")
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


class EmaCrossStrategy:
    """Emit a signal only on a completed-bar crossover; never uses future bars."""

    def __init__(self, fast_period: int = 9, slow_period: int = 21) -> None:
        if fast_period < 2 or slow_period < 3:
            raise ValueError("Use fast_period >= 2 and slow_period >= 3")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signals(self, bars: list[Bar]) -> list[Signal | None]:
        if any(bars[i].timestamp <= bars[i - 1].timestamp for i in range(1, len(bars))):
            raise ValueError("Bars must be strictly chronological")
        closes = [bar.close for bar in bars]
        fast = _ema(closes, self.fast_period)
        slow = _ema(closes, self.slow_period)
        signals: list[Signal | None] = [None] * len(bars)

        for index in range(1, len(bars)):
            if index < self.slow_period:
                continue
            crossed_up = fast[index - 1] <= slow[index - 1] and fast[index] > slow[index]
            crossed_down = fast[index - 1] >= slow[index - 1] and fast[index] < slow[index]
            if crossed_up:
                signals[index] = Signal(Side.LONG, "ema_cross_up")
            elif crossed_down:
                signals[index] = Signal(Side.SHORT, "ema_cross_down")
        return signals
