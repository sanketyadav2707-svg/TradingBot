"""Currency-safe monetary primitives and instrument economics.

The module intentionally accepts Decimal, integer, or decimal-string inputs.
Binary floats are rejected at the financial-domain boundary. Legacy float-based
interfaces remain adapters until their separately versioned migration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any


# ISO 4217 minor-unit exponents used by this project. This is an explicit,
# versioned supported subset, not a claim to be a complete live ISO registry.
CURRENCY_MINOR_UNITS: dict[str, int] = {
    "BHD": 3, "KWD": 3, "OMR": 3,
    "JPY": 0, "KRW": 0,
    "INR": 2, "USD": 2, "EUR": 2, "GBP": 2, "AED": 2, "SGD": 2,
    "AUD": 2, "CAD": 2, "CHF": 2, "CNY": 2, "HKD": 2, "NZD": 2,
}


def currency_minor_units(currency: str) -> int:
    if not isinstance(currency, str):
        raise TypeError("currency must be a string")
    code = currency.upper()
    try:
        return CURRENCY_MINOR_UNITS[code]
    except KeyError as exc:
        raise ValueError(f"unsupported_currency_code:{code}") from exc


def as_decimal(value: Any, field: str = "amount") -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field} must be Decimal, int, or decimal string; floats are forbidden")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a valid decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def quantum_for(currency: str) -> Decimal:
    return Decimal(1).scaleb(-currency_minor_units(currency))


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        code = self.currency.upper() if isinstance(self.currency, str) else ""
        minor_units = currency_minor_units(code)
        amount = as_decimal(self.amount)
        rounded = amount.quantize(Decimal(1).scaleb(-minor_units), rounding=ROUND_HALF_EVEN)
        object.__setattr__(self, "amount", rounded)
        object.__setattr__(self, "currency", code)

    @classmethod
    def of(cls, amount: Decimal | int | str, currency: str) -> "Money":
        return cls(as_decimal(amount), currency)

    def _same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError("money operation requires another Money value")
        if self.currency != other.currency:
            raise ValueError(f"currency_mismatch:{self.currency}:{other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def scale(self, factor: Decimal | int | str) -> "Money":
        return Money(self.amount * as_decimal(factor, "factor"), self.currency)

    def as_dict(self) -> dict[str, str]:
        return {"amount": format(self.amount, "f"), "currency": self.currency}


@dataclass(frozen=True, slots=True)
class InstrumentEconomics:
    """Exchange contract economics, separate from fees and account currency."""
    symbol: str
    tick_size: Decimal
    tick_value: Money
    point_value: Money
    # Quantities are raw exchange units; lot_size is the minimum lot size.
    lot_size: int = 1
    quantity_step: int = 1
    quantity_freeze: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("instrument symbol must be non-empty")
        tick_size = as_decimal(self.tick_size, "tick_size")
        if tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if not isinstance(self.tick_value, Money) or not isinstance(self.point_value, Money):
            raise TypeError("tick_value and point_value must be Money")
        if self.tick_value.currency != self.point_value.currency:
            raise ValueError("instrument_economics_currency_mismatch")
        if self.point_value.amount * tick_size != self.tick_value.amount:
            raise ValueError("tick_value_must_equal_tick_size_times_point_value")
        if type(self.lot_size) is not int or self.lot_size < 1:
            raise ValueError("lot_size must be a positive integer")
        if (
            type(self.quantity_step) is not int
            or self.quantity_step < self.lot_size
            or self.quantity_step % self.lot_size
        ):
            raise ValueError("quantity_step_must_be_a_multiple_of_lot_size")
        if type(self.quantity_freeze) is not int or self.quantity_freeze < self.lot_size:
            raise ValueError("quantity_freeze_must_be_at_least_one_lot")
        object.__setattr__(self, "tick_size", tick_size)


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    """Dated per-order-side fee components, all denominated in one currency.

    Values are per one tradable quantity unit. Exchange-specific tax bases and
    percentage charges must be calculated upstream and passed as explicit
    Money components; this object never guesses statutory tax rules.
    """
    schedule_id: str
    currency: str
    effective_from: str
    brokerage_per_unit_per_side: Money
    exchange_charge_per_unit_per_side: Money
    regulatory_charge_per_unit_per_side: Money
    taxes_per_unit_per_side: Money

    def __post_init__(self) -> None:
        if not self.schedule_id.strip():
            raise ValueError("schedule_id must be non-empty")
        currency = self.currency.upper()
        currency_minor_units(currency)
        object.__setattr__(self, "currency", currency)
        try:
            date.fromisoformat(self.effective_from)
        except (TypeError, ValueError) as exc:
            raise ValueError("effective_from must be an ISO date (YYYY-MM-DD)") from exc
        for name in (
            "brokerage_per_unit_per_side",
            "exchange_charge_per_unit_per_side",
            "regulatory_charge_per_unit_per_side",
            "taxes_per_unit_per_side",
        ):
            value = getattr(self, name)
            if not isinstance(value, Money) or value.currency != self.currency:
                raise ValueError(f"{name}_currency_mismatch")
            if value.amount < 0:
                raise ValueError(f"{name}_must_be_non_negative")
        if not self.effective_from:
            raise ValueError("effective_from must be explicit")

    @property
    def total_per_unit_per_side(self) -> Money:
        return (
            self.brokerage_per_unit_per_side
            + self.exchange_charge_per_unit_per_side
            + self.regulatory_charge_per_unit_per_side
            + self.taxes_per_unit_per_side
        )

    def round_trip(self, quantity: int) -> Money:
        if type(quantity) is not int or quantity < 1:
            raise ValueError("quantity must be a positive integer")
        return self.total_per_unit_per_side.scale(quantity * 2)
