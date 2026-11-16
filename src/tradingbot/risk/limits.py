"""Deterministic position sizing and drawdown gates using Decimal arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from tradingbot.money import FeeSchedule, Money, currency_minor_units
from tradingbot.models import Instrument


def _to_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return result


@dataclass(frozen=True, slots=True)
class RiskLimits:
    starting_balance_usd: Decimal | float = Decimal("50000.00")
    max_daily_loss_usd: Decimal | float = Decimal("300.00")
    max_total_drawdown_usd: Decimal | float = Decimal("1000.00")
    max_risk_per_trade_usd: Decimal | float = Decimal("50.00")
    max_contracts: int = 1
    max_trades_per_day: int = 4
    currency_code: str = "USD"

    def __post_init__(self) -> None:
        for field in (
            "starting_balance_usd",
            "max_daily_loss_usd",
            "max_total_drawdown_usd",
            "max_risk_per_trade_usd",
        ):
            try:
                amount = _to_decimal(getattr(self, field), field)
            except ValueError as exc:
                raise ValueError("All balance and risk limits must be finite and positive") from exc
            if amount <= 0:
                raise ValueError("All balance and risk limits must be finite and positive")
            object.__setattr__(self, field, amount)
        currency_minor_units(self.currency_code)
        object.__setattr__(self, "currency_code", self.currency_code.upper())
        if (
            type(self.max_contracts) is not int
            or type(self.max_trades_per_day) is not int
            or self.max_contracts < 1
            or self.max_trades_per_day < 1
        ):
            raise ValueError("Contract and trade limits must be positive integers")

    @property
    def starting_balance(self) -> Money:
        return Money.of(self.starting_balance_usd, self.currency_code)

    @property
    def daily_loss_limit(self) -> Money:
        return Money.of(self.max_daily_loss_usd, self.currency_code)

    @property
    def total_drawdown_limit(self) -> Money:
        return Money.of(self.max_total_drawdown_usd, self.currency_code)

    @property
    def risk_per_trade_limit(self) -> Money:
        return Money.of(self.max_risk_per_trade_usd, self.currency_code)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    quantity: int
    reason: str


class RiskGuard:
    """Size exchange orders in raw units after budgeting whole tradable lots.\n\n    Instrument tick/point values and fees are per raw quantity unit. ``max_contracts``\n    is retained as a compatibility name but caps whole lots; returned quantity is\n    the raw-unit amount to submit to the broker.\n    """

    def __init__(
        self,
        limits: RiskLimits,
        commission_per_contract_per_side_usd: Decimal | float = Decimal("0"),
        slippage_ticks_per_side: int = 1,
        fee_schedule: FeeSchedule | None = None,
    ) -> None:
        try:
            commission = _to_decimal(
                commission_per_contract_per_side_usd, "commission_per_contract_per_side"
            )
        except ValueError as exc:
            raise ValueError("Commission must be finite and non-negative") from exc
        if commission < 0:
            raise ValueError("Commission must be finite and non-negative")
        if type(slippage_ticks_per_side) is not int or slippage_ticks_per_side < 0:
            raise ValueError("Slippage ticks must be a non-negative integer")
        if fee_schedule is not None and not isinstance(fee_schedule, FeeSchedule):
            raise TypeError("fee_schedule must be a FeeSchedule")
        if fee_schedule is not None and fee_schedule.currency != limits.currency_code:
            raise ValueError("fee_schedule_currency_mismatch")
        self.limits = limits
        self.commission = commission
        self.fee_schedule = fee_schedule
        self.slippage_ticks = slippage_ticks_per_side

    def evaluate_entry(
        self,
        *,
        instrument: Instrument,
        stop_ticks: int,
        equity_usd: Decimal | float,
        peak_equity_usd: Decimal | float,
        daily_pnl_usd: Decimal | float,
        trades_today: int,
    ) -> RiskDecision:
        if instrument.currency_code != self.limits.currency_code:
            return RiskDecision(False, 0, "instrument_account_currency_mismatch")
        if type(stop_ticks) is not int or stop_ticks < 1:
            return RiskDecision(False, 0, "stop_distance_must_be_positive")
        try:
            equity = _to_decimal(equity_usd, "equity")
            peak_equity = _to_decimal(peak_equity_usd, "peak_equity")
            daily_pnl = _to_decimal(daily_pnl_usd, "daily_pnl")
            tick_value = _to_decimal(instrument.tick_value_usd, "tick_value")
        except ValueError:
            return RiskDecision(False, 0, "invalid_account_snapshot")
        if (
            type(trades_today) is not int
            or trades_today < 0
            or peak_equity < equity
        ):
            return RiskDecision(False, 0, "invalid_account_snapshot")
        if equity <= 0:
            return RiskDecision(False, 0, "non_positive_equity")
        if trades_today >= self.limits.max_trades_per_day:
            return RiskDecision(False, 0, "max_trades_per_day_reached")

        drawdown = max(Decimal("0"), peak_equity - equity)
        remaining_drawdown = self.limits.max_total_drawdown_usd - drawdown
        remaining_daily = self.limits.max_daily_loss_usd + daily_pnl
        if remaining_drawdown <= 0:
            return RiskDecision(False, 0, "maximum_total_drawdown_reached")
        if remaining_daily <= 0:
            return RiskDecision(False, 0, "maximum_daily_loss_reached")

        # tick_value and fees are per raw exchange quantity unit. Convert to
        # one tradable lot before applying max_contracts (which is lots).
        slippage_risk_per_unit = Decimal(2 * self.slippage_ticks) * tick_value
        stop_risk_per_unit = Decimal(stop_ticks) * tick_value
        round_trip_fees_per_unit = (
            self.fee_schedule.round_trip(1).amount
            if self.fee_schedule is not None
            else Decimal(2) * self.commission
        )
        estimated_risk_per_lot = (
            stop_risk_per_unit + slippage_risk_per_unit + round_trip_fees_per_unit
        ) * Decimal(instrument.lot_size)
        if estimated_risk_per_lot <= 0:
            return RiskDecision(False, 0, "invalid_risk_calculation")

        budget = min(
            self.limits.max_risk_per_trade_usd,
            remaining_daily,
            remaining_drawdown,
        )
        max_lots_by_risk = int(budget // estimated_risk_per_lot)
        max_lots_by_freeze = instrument.quantity_freeze // instrument.lot_size
        lot_increment = instrument.quantity_step // instrument.lot_size
        lots = min(
            self.limits.max_contracts,
            max_lots_by_risk,
            max_lots_by_freeze,
        )
        lots -= lots % lot_increment
        if lots < 1:
            if max_lots_by_freeze < 1:
                return RiskDecision(False, 0, "quantity_freeze_below_one_lot")
            return RiskDecision(False, 0, "risk_budget_too_small_for_one_lot")
        return RiskDecision(True, lots * instrument.lot_size, "approved")
