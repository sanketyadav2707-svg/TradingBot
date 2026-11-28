"""Net-of-costs option paper trade quality metrics, not a return forecast.

Uses realized trades only. Never interpret a high win rate as evidence of edge
without a protected out-of-sample test and live-quote execution validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingbot.risk.index_options import decimal


@dataclass(frozen=True, slots=True)
class OptionPerformance:
    trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: Decimal
    net_pnl: Decimal
    expectancy_per_trade: Decimal
    average_win: Decimal
    average_loss: Decimal
    profit_factor: Decimal | None
    max_drawdown: Decimal
    longest_losing_streak: int
    estimated_break_even_win_rate: Decimal | None
    profitable_after_costs: bool


def evaluate_option_performance(net_trade_pnls: tuple[Decimal, ...]) -> OptionPerformance:
    """Analyze *net realized* P&Ls including all applicable charges."""
    if not isinstance(net_trade_pnls, tuple) or not net_trade_pnls:
        raise ValueError("nonempty_realized_net_pnl_tuple_required")
    values = tuple(decimal(v, "net_trade_pnl") for v in net_trade_pnls)
    n = len(values)
    wins = [v for v in values if v > 0]
    losses = [-v for v in values if v < 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))
    avg_win = gross_profit / len(wins) if wins else Decimal("0")
    avg_loss = gross_loss / len(losses) if losses else Decimal("0")
    total = sum(values, Decimal("0"))
    peak = Decimal("0")
    running = Decimal("0")
    max_drawdown = Decimal("0")
    losing_streak = 0
    longest_streak = 0
    for value in values:
        running += value
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)
        losing_streak = losing_streak + 1 if value < 0 else 0
        longest_streak = max(longest_streak, losing_streak)
    return OptionPerformance(
        trades=n,
        wins=len(wins),
        losses=len(losses),
        breakeven=n-len(wins)-len(losses),
        win_rate=Decimal(len(wins)) / n,
        net_pnl=total,
        expectancy_per_trade=total / n,
        average_win=avg_win,
        average_loss=avg_loss,
        profit_factor=(gross_profit / gross_loss if gross_loss else None),
        max_drawdown=max_drawdown,
        longest_losing_streak=longest_streak,
        estimated_break_even_win_rate=(
            avg_loss / (avg_win + avg_loss) if avg_win + avg_loss > 0 else None
        ),
        profitable_after_costs=total > 0,
    )
