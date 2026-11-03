from datetime import datetime, timedelta, timezone

from tradingbot.models import Bar, Side
from tradingbot.strategy.ema_cross import EmaCrossStrategy


def _bars(prices: list[float]) -> list[Bar]:
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    return [
        Bar(start + timedelta(minutes=5 * i), "MES", p, p + 0.1, p - 0.1, p, 100)
        for i, p in enumerate(prices)
    ]


def test_ema_crossover_emits_event_only_on_cross() -> None:
    prices = [10, 9, 8, 9, 10, 11, 12, 13, 14]
    signals = EmaCrossStrategy(fast_period=2, slow_period=3).generate_signals(
        _bars(prices)
    )
    assert any(signal is not None and signal.side == Side.LONG for signal in signals)
    long_signals = [
        signal for signal in signals if signal is not None and signal.side == Side.LONG
    ]
    assert len(long_signals) == 1
