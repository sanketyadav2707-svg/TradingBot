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
