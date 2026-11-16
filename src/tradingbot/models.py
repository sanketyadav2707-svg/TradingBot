"""Core immutable domain models. All bar timestamps must be timezone-aware."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from math import isfinite

from tradingbot.money import InstrumentEconomics, Money, currency_minor_units


class DataValidationError(ValueError):
    """Raised when incoming market data is malformed or ambiguous."""


class Side(IntEnum):
    SHORT = -1
    FLAT = 0
    LONG = 1


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    tick_size: float
    tick_value_usd: float
    point_value_usd: float
    # Historical field names above are retained for API/database compatibility.
    # Their monetary denomination is currency_code, never implicitly USD.
    currency_code: str = "USD"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Instrument symbol cannot be empty")
        currency_minor_units(self.currency_code)
        object.__setattr__(self, "currency_code", self.currency_code.upper())
        if not all(isfinite(value) and value > 0 for value in (self.tick_size, self.tick_value_usd, self.point_value_usd)):
            raise ValueError("Instrument tick and point values must be finite and positive")
        expected = self.tick_size * self.point_value_usd
        if abs(expected - self.tick_value_usd) > max(1e-8, self.tick_value_usd * 1e-6):
            raise ValueError(
                "tick_value_usd must equal tick_size * point_value_usd; "
                f"expected {expected}, received {self.tick_value_usd}"
            )

    @property
    def tick_value(self) -> Money:
        """Currency-neutral monetary tick value; *_usd is a compatibility alias."""
        return Money.of(str(self.tick_value_usd), self.currency_code)

    @property
    def point_value(self) -> Money:
        """Currency-neutral monetary point value; *_usd is a compatibility alias."""
        return Money.of(str(self.point_value_usd), self.currency_code)

    @property
    def economics(self) -> InstrumentEconomics:
        """Exact Decimal contract economics with one-unit default lot metadata."""
        return InstrumentEconomics(
            symbol=self.symbol,
            tick_size=Decimal(str(self.tick_size)),
            tick_value=self.tick_value,
            point_value=self.point_value,
        )


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DataValidationError("Bar timestamp must include a timezone offset")
        if not self.symbol.strip():
            raise DataValidationError("Bar symbol cannot be empty")
        if not all(isfinite(value) for value in (self.open, self.high, self.low, self.close)):
            raise DataValidationError("OHLC prices must be finite numbers")
        if self.high < max(self.open, self.close, self.low):
            raise DataValidationError("High must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise DataValidationError("Low must be <= open, close, and high")
        if not isfinite(self.volume) or self.volume < 0:
            raise DataValidationError("Volume must be a finite, non-negative number")


@dataclass(frozen=True, slots=True)
class Signal:
    side: Side
    reason: str


@dataclass(frozen=True, slots=True)
class Trade:
    symbol: str
    side: Side
    quantity: int
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    gross_pnl_usd: float
    commission_usd: float
    net_pnl_usd: float
    bars_held: int
    exit_reason: str
    currency_code: str = "USD"

    @property
    def gross_pnl(self) -> Money:
        return Money.of(str(self.gross_pnl_usd), self.currency_code)

    @property
    def commission(self) -> Money:
        return Money.of(str(self.commission_usd), self.currency_code)

    @property
    def net_pnl(self) -> Money:
        return Money.of(str(self.net_pnl_usd), self.currency_code)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    symbol: str
    starting_balance_usd: float
    ending_balance_usd: float
    total_net_pnl_usd: float
    max_drawdown_usd: float
    trades: tuple[Trade, ...]
    currency_code: str = "USD"

    @property
    def starting_balance(self) -> Money:
        return Money.of(str(self.starting_balance_usd), self.currency_code)

    @property
    def ending_balance(self) -> Money:
        return Money.of(str(self.ending_balance_usd), self.currency_code)

    @property
    def total_net_pnl(self) -> Money:
        return Money.of(str(self.total_net_pnl_usd), self.currency_code)

    @property
    def max_drawdown(self) -> Money:
        return Money.of(str(self.max_drawdown_usd), self.currency_code)

    def metrics(self) -> dict[str, float | int | str | None]:
        count = len(self.trades)
        winners = [t.net_pnl_usd for t in self.trades if t.net_pnl_usd > 0]
        losers = [t.net_pnl_usd for t in self.trades if t.net_pnl_usd < 0]
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        longest_losing_streak = 0
        streak = 0
        for trade in self.trades:
            streak = streak + 1 if trade.net_pnl_usd < 0 else 0
            longest_losing_streak = max(longest_losing_streak, streak)
        return {
            "symbol": self.symbol,
            "currency_code": self.currency_code,
            "starting_balance_usd": round(self.starting_balance_usd, 2),
            "ending_balance_usd": round(self.ending_balance_usd, 2),
            "total_net_pnl_usd": round(self.total_net_pnl_usd, 2),
            "return_pct": round(100 * self.total_net_pnl_usd / self.starting_balance_usd, 4),
            "trades": count,
            "win_rate_pct": round(100 * len(winners) / count, 2) if count else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
            "expectancy_per_trade_usd": round(self.total_net_pnl_usd / count, 2) if count else 0.0,
            "max_drawdown_usd": round(self.max_drawdown_usd, 2),
            "longest_losing_streak": longest_losing_streak,
        }
