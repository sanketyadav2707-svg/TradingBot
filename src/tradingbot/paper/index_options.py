"""Offline index-option buying paper fills using executable quote sides.

The model intentionally has no broker connection or fabricated guaranteed stop.
It is in-memory only and is NOT restart-safe; durable accounting is an exit gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tradingbot.risk.index_options import (
    OptionContract, OptionDecision, OptionQuote, aware, decimal, option_quote_fingerprint,
)


@dataclass(frozen=True, slots=True)
class LongOptionPaperPosition:
    instrument_key: str
    quantity: int
    entry_timestamp: datetime
    entry_ask: Decimal
    debit: Decimal
    round_trip_fees: Decimal


@dataclass(frozen=True, slots=True)
class LongOptionPaperExit:
    instrument_key: str
    timestamp: datetime
    reason: str
    executable_bid: Decimal
    net_pnl: Decimal
    holding_seconds: int


class LongOptionPaperSimulator:
    """Risk-gated single-position simulator; does not connect to order router."""

    def __init__(
        self,
        *,
        stop_fraction: Decimal = Decimal("0.15"),
        target_fraction: Decimal = Decimal("0.30"),
        max_holding_seconds: int = 900,
        quote_max_age_seconds: int = 2,
    ) -> None:
        self.stop_fraction = decimal(stop_fraction, "stop_fraction")
        self.target_fraction = decimal(target_fraction, "target_fraction")
        if not (Decimal("0") < self.stop_fraction < Decimal("1")):
            raise ValueError("stop_fraction_must_be_between_zero_and_one")
        if self.target_fraction <= 0:
            raise ValueError("target_fraction_must_be_positive")
        if type(max_holding_seconds) is not int or not 180 <= max_holding_seconds <= 900:
            raise ValueError("holding_window_must_be_3_to_15_minutes")
        if type(quote_max_age_seconds) is not int or quote_max_age_seconds < 1:
            raise ValueError("quote_age_limit_invalid")
        self.max_holding_seconds = max_holding_seconds
        self.quote_max_age_seconds = quote_max_age_seconds
        self.position: LongOptionPaperPosition | None = None
        self.halted = False
        self.halt_reason: str | None = None
        self.realized_pnl = Decimal("0")

    def enter(self, *, decision: OptionDecision, contract: OptionContract, quote: OptionQuote) -> LongOptionPaperPosition:
        if self.halted:
            raise RuntimeError("option_simulator_halted")
        if self.position is not None:
            raise RuntimeError("simultaneous_option_positions_disabled")
        if not isinstance(decision, OptionDecision) or not decision.approved:
            raise ValueError("options_risk_gate_approval_required")
        if not isinstance(contract, OptionContract) or not isinstance(quote, OptionQuote):
            raise TypeError("option_contract_and_quote_required")
        if quote.instrument_key != contract.instrument_key:
            raise ValueError("paper_quote_contract_mismatch")
        if decision.quote_fingerprint != option_quote_fingerprint(quote):
            raise ValueError("risk_decision_bound_to_different_quote")
        if decision.quantity <= 0 or decision.quantity % contract.lot_size:
            raise ValueError("invalid_option_lot_quantity")
        if quote.ask * decision.quantity != decision.debit_rupees:
            raise ValueError("risk_decision_quote_changed_after_approval")
        if decision.worst_case_loss_rupees != decision.debit_rupees + decision.estimated_round_trip_fees:
            raise ValueError("risk_decision_fee_mismatch")
        self.position = LongOptionPaperPosition(
            instrument_key=contract.instrument_key,
            quantity=decision.quantity,
            entry_timestamp=quote.timestamp,
            entry_ask=quote.ask,
            debit=decision.debit_rupees,
            round_trip_fees=decision.estimated_round_trip_fees,
        )
        return self.position

    def evaluate_exit(
        self,
        *,
        quote: OptionQuote,
        now: datetime,
        extra_exit_slippage: Decimal = Decimal("0"),
    ) -> LongOptionPaperExit | None:
        if self.halted:
            raise RuntimeError("option_simulator_halted")
        if self.position is None:
            return None
        position = self.position
        if not isinstance(quote, OptionQuote):
            raise TypeError("option_quote_required")
        utc_now = aware(now, "now")
        quote_at = aware(quote.timestamp, "quote_timestamp")
        if quote.instrument_key != position.instrument_key:
            self.halted, self.halt_reason = True, "option_contract_mismatch"
            raise RuntimeError(self.halt_reason)
        age = (utc_now - quote_at).total_seconds()
        if age < 0 or age > self.quote_max_age_seconds:
            self.halted, self.halt_reason = True, "unreliable_option_exit_quote"
            raise RuntimeError(self.halt_reason)
        seconds = int((utc_now - aware(position.entry_timestamp, "entry_timestamp")).total_seconds())
        if seconds < 0:
            self.halted, self.halt_reason = True, "exit_before_entry"
            raise RuntimeError(self.halt_reason)
        stop = position.entry_ask * (Decimal("1") - self.stop_fraction)
        target = position.entry_ask * (Decimal("1") + self.target_fraction)
        if quote.bid <= stop:
            reason = "STOP_SIGNAL"
        elif quote.bid >= target:
            reason = "TAKE_PROFIT_SIGNAL"
        elif seconds >= self.max_holding_seconds:
            reason = "TIME_EXIT_SIGNAL"
        else:
            return None
        if quote.trading_halted or quote.bid_quantity < position.quantity:
            self.halted, self.halt_reason = True, "exit_depth_or_session_unavailable"
            raise RuntimeError(self.halt_reason)
        slippage = decimal(extra_exit_slippage, "extra_exit_slippage")
        if slippage < 0:
            raise ValueError("extra_exit_slippage_must_be_nonnegative")
        executable_bid = max(Decimal("0"), quote.bid - slippage)
        pnl = executable_bid * position.quantity - position.debit - position.round_trip_fees
        self.position = None
        self.realized_pnl += pnl
        return LongOptionPaperExit(
            instrument_key=position.instrument_key,
            timestamp=utc_now,
            reason=reason,
            executable_bid=executable_bid,
            net_pnl=pnl,
            holding_seconds=seconds,
        )

    def halt(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("operator_halt_reason_required")
        self.halted, self.halt_reason = True, reason.strip()
