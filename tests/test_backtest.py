from datetime import datetime, timedelta, timezone

from tradingbot.backtest.engine import BacktestConfig, BacktestEngine
from tradingbot.models import Bar, Instrument, Side, Signal
from tradingbot.risk.limits import RiskGuard, RiskLimits


class FixedSignalStrategy:
    def generate_signals(self, bars):
        # Signal is generated at bar 0 close, then entry is allowed at bar 1 open.
        return [Signal(Side.LONG, "test_entry")] + [None] * (len(bars) - 1)


def test_backtest_uses_next_bar_open_and_stops_conservatively() -> None:
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bars = [
        Bar(start, "MES", 100, 101, 99, 100, 10),
        Bar(start + timedelta(minutes=5), "MES", 100, 101, 97, 99, 10),
        Bar(start + timedelta(minutes=10), "MES", 99, 100, 98, 99, 10),
    ]
    instrument = Instrument("MES", 0.25, 1.25, 5.0)
    guard = RiskGuard(
        RiskLimits(
            starting_balance_usd=1_000,
            max_daily_loss_usd=300,
            max_total_drawdown_usd=500,
            max_risk_per_trade_usd=50,
            max_contracts=1,
        ),
        slippage_ticks_per_side=1,
    )
    engine = BacktestEngine(
        instrument,
        guard,
        FixedSignalStrategy(),
        BacktestConfig(stop_ticks=8, target_ticks=12, max_holding_bars=3),
    )
    result = engine.run(bars)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.entry_price == 100.25
    assert trade.exit_price == 98.0
    assert trade.net_pnl_usd < 0


def test_overnight_gap_exit_counts_toward_new_session_daily_loss() -> None:
    class TwoEntryStrategy:
        def generate_signals(self, bars):
            return [
                Signal(Side.LONG, "first_entry"),
                None,
                Signal(Side.LONG, "second_entry"),
                None,
                None,
            ]

    day_one = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bars = [
        Bar(day_one, "MES", 100, 101, 99, 100, 10),
        Bar(day_one + timedelta(minutes=5), "MES", 100, 101, 99, 100, 10),
        Bar(day_one + timedelta(days=1), "MES", 90, 91, 89, 90, 10),
        Bar(day_one + timedelta(days=1, minutes=5), "MES", 90, 91, 89, 90, 10),
        Bar(day_one + timedelta(days=1, minutes=10), "MES", 90, 91, 89, 90, 10),
    ]
    guard = RiskGuard(
        RiskLimits(
            starting_balance_usd=1_000,
            max_daily_loss_usd=30,
            max_total_drawdown_usd=500,
            max_risk_per_trade_usd=10,
            max_contracts=1,
            max_trades_per_day=4,
        ),
        slippage_ticks_per_side=0,
    )
    engine = BacktestEngine(
        Instrument("MES", 0.25, 1.25, 5.0),
        guard,
        TwoEntryStrategy(),
        BacktestConfig(stop_ticks=8, target_ticks=12, max_holding_bars=20),
    )
    result = engine.run(bars)

    # The first position is closed at the next session's open for a $50 loss.
    # That loss must remain in the new session's daily PnL and block entry two.
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "session_day_change"
    assert result.trades[0].net_pnl_usd == -50.0


def test_backtest_config_requires_positive_integer_bar_settings() -> None:
    import pytest

    with pytest.raises(ValueError, match="positive integers"):
        BacktestConfig(stop_ticks=1.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive integers"):
        BacktestConfig(max_holding_bars=True)  # type: ignore[arg-type]
