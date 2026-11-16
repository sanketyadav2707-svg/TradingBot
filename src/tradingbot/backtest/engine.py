"""Conservative bar-based backtester.

Signals are generated after a bar closes and can only execute at the next bar open.
If a stop and target are both touched in one OHLC bar, the stop is assumed first.
This remains an approximation: OHLC bars cannot reproduce queue position or true fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from tradingbot.compliance.rules import FirmComplianceGate
from tradingbot.models import BacktestResult, Bar, Instrument, Side, Trade
from tradingbot.money import Money
from tradingbot.risk.limits import RiskGuard
from tradingbot.strategy.ema_cross import EmaCrossStrategy


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    stop_ticks: int = 8
    target_ticks: int = 12
    max_holding_bars: int = 3
    session_timezone: str = "America/New_York"

    def __post_init__(self) -> None:
        values = (self.stop_ticks, self.target_ticks, self.max_holding_bars)
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError("Stop, target, and max holding bars must be positive integers")
        ZoneInfo(self.session_timezone)


@dataclass(slots=True)
class _Position:
    side: Side
    quantity: int
    entry_time: datetime
    entry_index: int
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal


class BacktestEngine:
    def __init__(
        self,
        instrument: Instrument,
        risk_guard: RiskGuard,
        strategy: EmaCrossStrategy,
        config: BacktestConfig | None = None,
        compliance_gate: FirmComplianceGate | None = None,
    ) -> None:
        self.instrument = instrument
        self.risk_guard = risk_guard
        self.strategy = strategy
        self.config = config or BacktestConfig()
        self.compliance_gate = compliance_gate

    def run(self, bars: list[Bar]) -> BacktestResult:
        if len(bars) < 3:
            raise ValueError("At least three bars are required")
        if any(bar.symbol != self.instrument.symbol for bar in bars):
            raise ValueError("All bar symbols must match the configured instrument")
        signals = self.strategy.generate_signals(bars)
        slip = self.risk_guard.slippage_ticks
        tick_size = Decimal(str(self.instrument.tick_size))
        point_value = Decimal(str(self.instrument.point_value_usd))
        slip_price = Decimal(slip) * tick_size
        commission = self.risk_guard.commission

        starting_balance = self.risk_guard.limits.starting_balance_usd
        balance = starting_balance
        peak_equity = balance
        max_drawdown = Decimal("0")
        daily_pnl = Decimal("0")
        trades_today = 0
        current_day: date | None = None
        position: _Position | None = None
        trades: list[Trade] = []
        session_tz = ZoneInfo(self.config.session_timezone)

        def close_position(
            pos: _Position, bar: Bar, base_price: float, reason: str, index: int
        ) -> Trade:
            nonlocal balance, peak_equity, max_drawdown, daily_pnl
            exit_price = Decimal(str(base_price)) - Decimal(int(pos.side)) * slip_price
            gross_raw = (
                (exit_price - pos.entry_price)
                * Decimal(int(pos.side))
                * point_value
                * Decimal(pos.quantity)
            )
            gross = Money(gross_raw, self.instrument.currency_code).amount
            fees = Money(Decimal("2") * commission * Decimal(pos.quantity), self.instrument.currency_code).amount
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
                entry_price=float(pos.entry_price),
                exit_price=float(exit_price),
                gross_pnl_usd=float(gross),
                commission_usd=float(fees),
                net_pnl_usd=float(net),
                bars_held=max(1, index - pos.entry_index + 1),
                exit_reason=reason,
                currency_code=self.instrument.currency_code,
            )

        for index in range(1, len(bars)):
            bar = bars[index]
            bar_day = bar.timestamp.astimezone(session_tz).date()
            previous_day = bars[index - 1].timestamp.astimezone(session_tz).date()
            if current_day != bar_day:
                # Attribute an overnight position's opening-gap exit to the new
                # session. Resetting after close would silently erase that day's PnL
                # from the daily-loss gate.
                daily_pnl = 0.0
                trades_today = 0
                current_day = bar_day
                if position is not None:
                    trades.append(
                        close_position(position, bar, bar.open, "session_day_change", index)
                    )
                    position = None

            if position is not None and self.compliance_gate is not None:
                flatten_decision = self.compliance_gate.must_flatten(bar.timestamp)
                if flatten_decision.allowed:
                    trades.append(
                        close_position(position, bar, bar.open, flatten_decision.reason, index)
                    )
                    position = None

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
                if decision.approved and self.compliance_gate is not None:
                    compliance = self.compliance_gate.check_entry(
                        timestamp=bar.timestamp,
                        symbol=self.instrument.symbol,
                        quantity=decision.quantity,
                    )
                    if not compliance.allowed:
                        decision = type(decision)(False, 0, compliance.reason)
                if decision.approved:
                    direction = int(signal.side)
                    bar_open = Decimal(str(bar.open))
                    entry_price = bar_open + Decimal(direction) * slip_price
                    stop_price = (
                        entry_price - Decimal(direction * self.config.stop_ticks) * tick_size
                    )
                    target_price = (
                        entry_price + Decimal(direction * self.config.target_ticks) * tick_size
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
                    stop_hit = Decimal(str(bar.low)) <= position.stop_price
                    target_hit = Decimal(str(bar.high)) >= position.target_price
                else:
                    stop_hit = Decimal(str(bar.high)) >= position.stop_price
                    target_hit = Decimal(str(bar.low)) <= position.target_price

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
                    trades.append(close_position(position, bar, Decimal(str(bar.close)), "time_exit", index))
                    position = None

        if position is not None:
            final_bar = bars[-1]
            trades.append(
                close_position(position, final_bar, Decimal(str(final_bar.close)), "end_of_data", len(bars) - 1)
            )

        return BacktestResult(
            symbol=self.instrument.symbol,
            starting_balance_usd=float(starting_balance),
            ending_balance_usd=float(balance),
            total_net_pnl_usd=float(balance - starting_balance),
            max_drawdown_usd=float(max_drawdown),
            trades=tuple(trades),
            currency_code=self.instrument.currency_code,
        )
