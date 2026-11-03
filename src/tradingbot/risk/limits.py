"""Deterministic position sizing and drawdown gates."""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.models import Instrument


@dataclass(frozen=True, slots=True)
class RiskLimits:
    starting_balance_usd: float = 50_000.0
    max_daily_loss_usd: float = 300.0
    max_total_drawdown_usd: float = 1_000.0
    max_risk_per_trade_usd: float = 50.0
    max_contracts: int = 1
    max_trades_per_day: int = 4

    def __post_init__(self) -> None:
        numeric = (
            self.starting_balance_usd,
            self.max_daily_loss_usd,
            self.max_total_drawdown_usd,
            self.max_risk_per_trade_usd,
        )
        if any(value <= 0 for value in numeric):
            raise ValueError("All balance and risk limits must be positive")
        if self.max_contracts < 1 or self.max_trades_per_day < 1:
            raise ValueError("Contract and trade limits must be at least 1")


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    quantity: int
    reason: str


class RiskGuard:
    """Size a single entry using stop distance and a conservative friction estimate."""

    def __init__(
        self,
        limits: RiskLimits,
        commission_per_contract_per_side_usd: float = 0.0,
        slippage_ticks_per_side: int = 1,
    ) -> None:
        if commission_per_contract_per_side_usd < 0 or slippage_ticks_per_side < 0:
            raise ValueError("Commission and slippage assumptions cannot be negative")
        self.limits = limits
        self.commission = commission_per_contract_per_side_usd
        self.slippage_ticks = slippage_ticks_per_side

    def evaluate_entry(
        self,
        *,
        instrument: Instrument,
        stop_ticks: int,
        equity_usd: float,
        peak_equity_usd: float,
        daily_pnl_usd: float,
        trades_today: int,
    ) -> RiskDecision:
        if stop_ticks < 1:
            return RiskDecision(False, 0, "stop_distance_must_be_positive")
        if trades_today >= self.limits.max_trades_per_day:
            return RiskDecision(False, 0, "max_trades_per_day_reached")

        drawdown = max(0.0, peak_equity_usd - equity_usd)
        remaining_drawdown = self.limits.max_total_drawdown_usd - drawdown
        remaining_daily = self.limits.max_daily_loss_usd + daily_pnl_usd
        if remaining_drawdown <= 0:
            return RiskDecision(False, 0, "maximum_total_drawdown_reached")
        if remaining_daily <= 0:
            return RiskDecision(False, 0, "maximum_daily_loss_reached")
        if equity_usd <= 0:
            return RiskDecision(False, 0, "non_positive_equity")

        slippage_risk = 2 * self.slippage_ticks * instrument.tick_value_usd
        stop_risk = stop_ticks * instrument.tick_value_usd
        round_trip_commission = 2 * self.commission
        estimated_risk_per_contract = (
            stop_risk + slippage_risk + round_trip_commission
        )
        budget = min(
            self.limits.max_risk_per_trade_usd,
            remaining_daily,
            remaining_drawdown,
        )
        quantity = min(
            self.limits.max_contracts,
            int(budget // estimated_risk_per_contract),
        )
        if quantity < 1:
            return RiskDecision(False, 0, "risk_budget_too_small_for_one_contract")
        return RiskDecision(True, quantity, "approved")
