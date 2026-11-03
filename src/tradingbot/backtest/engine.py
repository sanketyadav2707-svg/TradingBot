"""Conservative bar-based backtester.

Signals are generated after a bar closes and can only execute at the next bar open.
If a stop and target are both touched in one OHLC bar, the stop is assumed first.
This remains an approximation: OHLC bars cannot reproduce queue position or true fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from tradingbot.models import BacktestResult, Bar, Instrument, Side, Trade
from tradingbot.risk.limits import RiskGuard
from tradingbot.strategy.ema_cross import EmaCrossStrategy


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    stop_ticks: int = 8
    target_ticks: int = 12
    max_holding_bars: int = 3
    session_timezone: str = "America/New_York"

    def __post_init__(self) -> None:
        if min(self.stop_ticks, self.target_ticks, self.max_holding_bars) < 1:
            raise ValueError("Stop, target, and max holding bars must be positive")
        ZoneInfo(self.session_timezone)


@dataclass(slots=True)
class _Position:
    side: Side
    quantity: int
    entry_time: datetime
    entry_index: int
    entry_price: float
    stop_price: float
    target_price: float


class BacktestEngine:
    def __init__(
        self,
        instrument: Instrument,
        risk_guard: RiskGuard,
        strategy: EmaCrossStrategy,
        config: BacktestConfig | None = None,
    ) -> None:
        self.instrument = instrument
        self.risk_guard = risk_guard
        self.strategy = strategy
        self.config = config or BacktestConfig()

    def run(self, bars: list[Bar]) -> BacktestResult:
        if len(bars) < 3:
            raise ValueError("At least three bars are required")
        if any(bar.symbol != self.instrument.symbol for bar in bars):
            raise ValueError("All bar symbols must match the configured instrument")
        signals = self.strategy.generate_signals(bars)
        slip = self.risk_guard.slippage_ticks
        slip_price = slip * self.instrument.tick_size
        commission = self.risk_guard.commission

        balance = self.risk_guard.limits.starting_balance_usd
        peak_equity = balance
        max_drawdown = 0.0
        daily_pnl = 0.0
        trades_today = 0
        current_day: date | None = None
        position: _Position | None = None
        trades: list[Trade] = []
        session_tz = ZoneInfo(self.config.session_timezone)

        def close_position(
            pos: _Position, bar: Bar, base_price: float, reason: str, index: int
        ) -> Trade:
            nonlocal balance, peak_equity, max_drawdown, daily_pnl
            exit_price = base_price - int(pos.side) * slip_price
            gross = (
                (exit_price - pos.entry_price)
                * int(pos.side)
                * self.instrument.point_value_usd
                * pos.quantity
            )
            fees = 2.0 * commission * pos.quantity
            net = gross - fees
            balance += net
            daily_pnl += net
            peak_equity = max(peak_equity, balance)
            max_drawdown = max(max_drawdown, peak_equity - balance)
            return Trade(
                symbol=self.instrument.symbol,
                side=pos.side,
                quantity=pos.quantity,
                entry_time=pos.entry_time,
                exit_time=bar.timestamp,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                gross_pnl_usd=gross,
                commission_usd=fees,
                net_pnl_usd=net,
                bars_held=max(1, index - pos.entry_index + 1),
                exit_reason=reason,
            )

        for index in range(1, len(bars)):
            bar = bars[index]
            bar_day = bar.timestamp.astimezone(session_tz).date()
            previous_day = bars[index - 1].timestamp.astimezone(session_tz).date()
            if current_day != bar_day:
                if position is not None:
                    trades.append(close_position(position, bar, bar.open, "session_day_change", index))
                    position = None
                current_day = bar_day
                daily_pnl = 0.0
                trades_today = 0

            signal = signals[index - 1] if previous_day == bar_day else None
            if position is not None and signal is not None and signal.side == Side(-int(position.side)):
                trades.append(close_position(position, bar, bar.open, "opposite_signal", index))
                position = None

            if position is None and signal is not None and signal.side != Side.FLAT:
                decision = self.risk_guard.evaluate_entry(
                    instrument=self.instrument,
                    stop_ticks=self.config.stop_ticks,
                    equity_usd=balance,
                    peak_equity_usd=peak_equity,
                    daily_pnl_usd=daily_pnl,
                    trades_today=trades_today,
                )
                if decision.approved:
                    direction = int(signal.side)
                    entry_price = bar.open + direction * slip_price
                    stop_price = (
                        entry_price - direction * self.config.stop_ticks * self.instrument.tick_size
                    )
                    target_price = (
                        entry_price + direction * self.config.target_ticks * self.instrument.tick_size
                    )
                    position = _Position(
                        side=signal.side,
                        quantity=decision.quantity,
                        entry_time=bar.timestamp,
                        entry_index=index,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        target_price=target_price,
                    )
                    trades_today += 1

            if position is not None:
                if position.side == Side.LONG:
                    stop_hit = bar.low <= position.stop_price
                    target_hit = bar.high >= position.target_price
                else:
                    stop_hit = bar.high >= position.stop_price
                    target_hit = bar.low <= position.target_price

                if stop_hit:
                    trades.append(
                        close_position(position, bar, position.stop_price, "stop_loss", index)
                    )
                    position = None
                elif target_hit:
                    trades.append(
                        close_position(position, bar, position.target_price, "take_profit", index)
                    )
                    position = None
                elif index - position.entry_index + 1 >= self.config.max_holding_bars:
                    trades.append(close_position(position, bar, bar.close, "time_exit", index))
                    position = None

        if position is not None:
            final_bar = bars[-1]
            trades.append(
                close_position(position, final_bar, final_bar.close, "end_of_data", len(bars) - 1)
            )

        return BacktestResult(
            symbol=self.instrument.symbol,
            starting_balance_usd=self.risk_guard.limits.starting_balance_usd,
            ending_balance_usd=balance,
            total_net_pnl_usd=balance - self.risk_guard.limits.starting_balance_usd,
            max_drawdown_usd=max_drawdown,
            trades=tuple(trades),
        )
