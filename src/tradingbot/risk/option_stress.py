"""Adversarial long-index-option paper P&L stress testing.

Every scenario assumes one long option entered at the quoted ask, with
specified exit bid and explicit fees. No order fills, option pricing model,
or trading profitability is implied. The loss can equal full debit plus fees.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingbot.risk.index_options import OptionDecision, decimal


@dataclass(frozen=True, slots=True)
class OptionShock:
    name: str
    exit_bid: Decimal
    additional_exit_slippage: Decimal = Decimal("0")
    extra_fees: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("shock_name_required")
        for field in ("exit_bid", "additional_exit_slippage", "extra_fees"):
            value = decimal(getattr(self, field), field)
            if value < 0:
                raise ValueError(field + "_must_be_nonnegative")
            object.__setattr__(self, field, value)


@dataclass(frozen=True, slots=True)
class OptionShockResult:
    name: str
    net_pnl_rupees: Decimal
    loss_fraction_of_equity: Decimal
    final_exit_bid: Decimal
    profitable: bool


@dataclass(frozen=True, slots=True)
class OptionStressReport:
    quantity: int
    entry_debit: Decimal
    modeled_fees: Decimal
    break_even_exit_bid: Decimal
    worst_modeled_loss: Decimal
    scenarios: tuple[OptionShockResult, ...]


def stress_test_long_option(
    *,
    entry_decision: OptionDecision,
    equity: Decimal,
    shocks: tuple[OptionShock, ...],
) -> OptionStressReport:
    """Model realized exit P&L under explicitly supplied adverse conditions.

    This computes a fixed-quantity *paper* accounting identity. It does not
    estimate a probability distribution or establish a risk-limited stop.
    """
    if not isinstance(entry_decision, OptionDecision):
        raise TypeError("option_decision_required")
    if not entry_decision.approved or entry_decision.quantity <= 0:
        raise ValueError("approved_paper_option_decision_required")
    amount = decimal(equity, "equity")
    if amount <= 0:
        raise ValueError("equity_must_be_positive")
    if not isinstance(shocks, tuple) or not shocks or not all(isinstance(x, OptionShock) for x in shocks):
        raise ValueError("nonempty_tuple_of_shocks_required")
    qty = entry_decision.quantity
    entry_debit = entry_decision.debit_rupees
    base_fees = entry_decision.estimated_round_trip_fees
    modeled = []
    for shock in shocks:
        executable_bid = max(Decimal("0"), shock.exit_bid - shock.additional_exit_slippage)
        proceeds = executable_bid * qty
        pnl = proceeds - entry_debit - base_fees - shock.extra_fees
        modeled.append(OptionShockResult(
            name=shock.name,
            net_pnl_rupees=pnl,
            loss_fraction_of_equity=max(Decimal("0"), -pnl) / amount,
            final_exit_bid=executable_bid,
            profitable=pnl > 0,
        ))
    return OptionStressReport(
        quantity=qty,
        entry_debit=entry_debit,
        modeled_fees=base_fees,
        break_even_exit_bid=(entry_debit + base_fees) / qty,
        worst_modeled_loss=min(result.net_pnl_rupees for result in modeled),
        scenarios=tuple(modeled),
    )
