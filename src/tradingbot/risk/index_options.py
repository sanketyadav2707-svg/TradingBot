"""Index-option BUY-only pre-trade safety gate, independent of broker routing.

This is an *offline* defense-in-depth gate. It never grants permission to submit
a live order or claims a stop guarantees the loss bound. Full debit at ask plus
fees is the conservative exposure-at-risk for an unhedged bought option.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
D = Decimal


def decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(field + "_requires_exact_decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(field + "_invalid_decimal") from exc
    if not result.is_finite():
        raise ValueError(field + "_must_be_finite")
    return result


def aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(field + "_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


class Right(str, Enum):
    CALL = "CE"
    PUT = "PE"


@dataclass(frozen=True, slots=True)
class OptionContract:
    instrument_key: str
    underlying: str
    exchange: str
    right: Right
    strike: Decimal
    expiry: date
    lot_size: int
    tick_size: Decimal
    quantity_freeze: int
    master_verified_at: datetime
    master_source: str

    def __post_init__(self) -> None:
        if self.exchange not in {"NSE", "BSE"}:
            raise ValueError("unsupported_exchange")
        if self.underlying not in {"NIFTY", "SENSEX"}:
            raise ValueError("unsupported_underlying")
        if (self.exchange, self.underlying) not in {("NSE", "NIFTY"), ("BSE", "SENSEX")}:
            raise ValueError("underlying_exchange_mismatch")
        if not isinstance(self.right, Right):
            raise ValueError("option_right_must_be_CE_or_PE")
        if not isinstance(self.instrument_key, str) or not self.instrument_key.strip():
            raise ValueError("instrument_key_required")
        if self.exchange == "NSE" and not self.instrument_key.startswith("NSE_FO|"):
            raise ValueError("nse_option_key_must_match_exchange")
        if self.exchange == "BSE" and not self.instrument_key.startswith("BSE_FO|"):
            raise ValueError("bse_option_key_must_match_exchange")
        if not isinstance(self.expiry, date) or isinstance(self.expiry, datetime):
            raise ValueError("expiry_must_be_date")
        if any(type(x) is not int or x < 1 for x in (self.lot_size, self.quantity_freeze)):
            raise ValueError("lot_and_freeze_must_be_positive_integers")
        if self.quantity_freeze < self.lot_size:
            raise ValueError("freeze_below_lot_size")
        for key in ("strike", "tick_size"):
            value = decimal(getattr(self, key), key)
            if value <= 0:
                raise ValueError(key + "_must_be_positive")
            object.__setattr__(self, key, value)
        aware(self.master_verified_at, "master_verified_at")
        if not isinstance(self.master_source, str) or not self.master_source.startswith("https://"):
            raise ValueError("official_master_source_required")


@dataclass(frozen=True, slots=True)
class OptionQuote:
    timestamp: datetime
    instrument_key: str
    bid: Decimal
    ask: Decimal
    bid_quantity: int
    ask_quantity: int
    underlying_price: Decimal
    underlying_timestamp: datetime
    implied_volatility: Decimal
    open_interest: int
    trading_halted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_key, str) or not self.instrument_key.strip():
            raise ValueError("quote_instrument_key_required")
        aware(self.timestamp, "quote_timestamp")
        aware(self.underlying_timestamp, "underlying_timestamp")
        for field in ("bid", "ask", "underlying_price", "implied_volatility"):
            value = decimal(getattr(self, field), field)
            if value <= 0:
                raise ValueError(field + "_must_be_positive")
            object.__setattr__(self, field, value)
        if self.ask < self.bid:
            raise ValueError("crossed_quote_rejected")
        for field in ("bid_quantity", "ask_quantity", "open_interest"):
            if type(getattr(self, field)) is not int or getattr(self, field) < 0:
                raise ValueError(field + "_invalid")
        if type(self.trading_halted) is not bool:
            raise ValueError("trading_halted_must_be_bool")


@dataclass(frozen=True, slots=True)
class OptionAccount:
    equity: Decimal
    available_cash: Decimal
    daily_realized_pnl: Decimal
    peak_equity: Decimal
    open_option_debit: Decimal
    trades_today: int
    open_positions: int
    unresolved_orders: int
    risk_halted: bool
    reconciled: bool

    def __post_init__(self) -> None:
        for name in ("equity", "available_cash", "daily_realized_pnl", "peak_equity", "open_option_debit"):
            value = decimal(getattr(self, name), name)
            object.__setattr__(self, name, value)
        if self.equity <= 0 or self.peak_equity <= 0 or self.available_cash < 0 or self.open_option_debit < 0:
            raise ValueError("invalid_account_economics")
        if any(type(getattr(self, key)) is not int or getattr(self, key) < 0
               for key in ("trades_today", "open_positions", "unresolved_orders")):
            raise ValueError("invalid_account_counters")
        if type(self.risk_halted) is not bool or type(self.reconciled) is not bool:
            raise ValueError("invalid_account_health_flags")


@dataclass(frozen=True, slots=True)
class OptionRiskPolicy:
    max_full_premium_risk_fraction: Decimal = D("0.02")
    max_total_option_debit_fraction: Decimal = D("0.05")
    daily_loss_fraction: Decimal = D("0.02")
    peak_drawdown_fraction: Decimal = D("0.06")
    max_spread_fraction: Decimal = D("0.015")
    max_moneyness_fraction: Decimal = D("0.01")
    max_iv: Decimal = D("1.50")
    max_quote_age_seconds: int = 2
    max_master_age_hours: int = 24
    min_days_to_expiry: int = 1
    max_days_to_expiry: int = 14
    max_trades_per_day: int = 3
    min_open_interest: int = 100
    session_entry_start: time = time(9, 25)
    session_entry_end: time = time(14, 45)

    def __post_init__(self) -> None:
        for name in ("max_full_premium_risk_fraction", "max_total_option_debit_fraction",
                     "daily_loss_fraction", "peak_drawdown_fraction", "max_spread_fraction",
                     "max_moneyness_fraction", "max_iv"):
            value = decimal(getattr(self, name), name)
            if value <= 0:
                raise ValueError(name + "_must_be_positive")
            object.__setattr__(self, name, value)
        for name in ("max_full_premium_risk_fraction", "max_total_option_debit_fraction",
                     "daily_loss_fraction", "peak_drawdown_fraction", "max_spread_fraction"):
            if getattr(self, name) > 1:
                raise ValueError(name + "_cannot_exceed_one")
        for name in ("max_quote_age_seconds", "max_master_age_hours", "max_days_to_expiry",
                     "max_trades_per_day", "min_open_interest"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(name + "_must_be_positive_int")
        if type(self.min_days_to_expiry) is not int or self.min_days_to_expiry < 0:
            raise ValueError("min_days_to_expiry_invalid")
        if self.min_days_to_expiry > self.max_days_to_expiry:
            raise ValueError("expiry_window_invalid")
        if not isinstance(self.session_entry_start, time) or not isinstance(self.session_entry_end, time):
            raise ValueError("session_times_required")
        if self.session_entry_start.tzinfo or self.session_entry_end.tzinfo or self.session_entry_end <= self.session_entry_start:
            raise ValueError("entry_session_window_invalid")


def option_quote_fingerprint(quote: OptionQuote) -> str:
    """Bind a paper decision to the exact option quote snapshot it evaluated."""
    if not isinstance(quote, OptionQuote):
        raise TypeError("option_quote_required")
    values = (
        quote.instrument_key, aware(quote.timestamp, "quote_timestamp").isoformat(),
        str(quote.bid), str(quote.ask), str(quote.bid_quantity), str(quote.ask_quantity),
        str(quote.underlying_price),
        aware(quote.underlying_timestamp, "underlying_timestamp").isoformat(),
        str(quote.implied_volatility), str(quote.open_interest), str(quote.trading_halted),
    )
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OptionDecision:
    approved: bool
    reason: str
    quantity: int
    debit_rupees: Decimal
    worst_case_loss_rupees: Decimal
    estimated_round_trip_fees: Decimal
    spread_fraction: Decimal
    quote_fingerprint: str = ""


def evaluate_long_option_entry(
    *,
    now: datetime,
    contract: OptionContract,
    quote: OptionQuote,
    account: OptionAccount,
    policy: OptionRiskPolicy,
    lots: int,
    round_trip_fees_rupees: Decimal,
    official_session_verified: bool,
    data_feed_healthy: bool,
    option_master_matches_quote: bool,
    broker_permissions_verified: bool,
) -> OptionDecision:
    """Allow one fully paid LONG option paper entry only if all gates pass.

    A buy-side stop is deliberately *not* used as a guaranteed risk bound:
    the entire option premium may be lost. Fees must be externally verified.
    """
    utc_now = aware(now, "now")
    if not all(isinstance(x, cls) for x, cls in (
        (contract, OptionContract), (quote, OptionQuote),
        (account, OptionAccount), (policy, OptionRiskPolicy)
    )):
        raise TypeError("options_gate_inputs_required")
    if type(lots) is not int or lots < 1:
        raise ValueError("lots_must_be_positive_integer")
    fees = decimal(round_trip_fees_rupees, "round_trip_fees")
    if fees < 0:
        raise ValueError("round_trip_fees_cannot_be_negative")
    quantity = lots * contract.lot_size
    debit = quote.ask * quantity
    worst = debit + fees
    spread = (quote.ask - quote.bid) / quote.ask
    quote_id = option_quote_fingerprint(quote)

    def reject(reason: str) -> OptionDecision:
        return OptionDecision(False, reason, 0, debit, worst, fees, spread, quote_id)

    flags = {
        "exchange_session_unverified": official_session_verified,
        "market_feed_unhealthy": data_feed_healthy,
        "option_contract_not_reconciled": option_master_matches_quote,
        "broker_permissions_unverified": broker_permissions_verified,
    }
    if any(type(value) is not bool for value in flags.values()):
        raise TypeError("gate_flags_must_be_booleans")
    for failure, passed in flags.items():
        if not passed:
            return reject(failure)
    if quote.instrument_key != contract.instrument_key:
        return reject("option_quote_instrument_key_mismatch")
    if account.risk_halted or not account.reconciled or account.unresolved_orders:
        return reject("account_halted_unreconciled_or_orders_unresolved")
    if account.open_positions != 0 or account.open_option_debit != 0:
        return reject("simultaneous_option_positions_disabled")
    if account.trades_today >= policy.max_trades_per_day:
        return reject("daily_trade_limit_reached")
    if account.peak_equity - account.equity >= account.peak_equity * policy.peak_drawdown_fraction:
        return reject("equity_drawdown_limit_reached")
    if account.daily_realized_pnl <= -account.peak_equity * policy.daily_loss_fraction:
        return reject("daily_loss_limit_reached")
    if quantity > contract.quantity_freeze:
        return reject("exchange_quantity_freeze_exceeded")
    if utc_now < aware(quote.timestamp, "quote_timestamp") or utc_now < aware(quote.underlying_timestamp, "underlying_timestamp"):
        return reject("future_dated_market_quote")
    if (utc_now - aware(quote.timestamp, "quote_timestamp")).total_seconds() > policy.max_quote_age_seconds:
        return reject("option_quote_stale")
    if (utc_now - aware(quote.underlying_timestamp, "underlying_timestamp")).total_seconds() > policy.max_quote_age_seconds:
        return reject("underlying_quote_stale")
    if contract.master_verified_at > now:
        return reject("instrument_master_future_dated")
    if now - contract.master_verified_at > timedelta(hours=policy.max_master_age_hours):
        return reject("instrument_master_stale")
    if quote.trading_halted:
        return reject("market_halt_active")
    local_now = utc_now.astimezone(IST)
    if not policy.session_entry_start <= local_now.time().replace(tzinfo=None) < policy.session_entry_end:
        return reject("outside_entry_window")
    dte = (contract.expiry - local_now.date()).days
    if not policy.min_days_to_expiry <= dte <= policy.max_days_to_expiry:
        return reject("expiry_risk_outside_policy")
    if quote.bid_quantity < quantity or quote.ask_quantity < quantity:
        return reject("insufficient_top_of_book_depth")
    if quote.open_interest < policy.min_open_interest:
        return reject("insufficient_open_interest")
    if spread > policy.max_spread_fraction:
        return reject("bid_ask_spread_too_wide")
    if abs(contract.strike - quote.underlying_price) / quote.underlying_price > policy.max_moneyness_fraction:
        return reject("strike_too_far_from_atm")
    if quote.implied_volatility > policy.max_iv:
        return reject("implied_volatility_above_limit")
    if contract.strike % contract.tick_size != 0 or quote.ask % contract.tick_size != 0 or quote.bid % contract.tick_size != 0:
        return reject("non_tick_aligned_quote_or_strike")
    if worst > account.available_cash:
        return reject("insufficient_cash_for_full_debit")
    if worst > account.equity * policy.max_full_premium_risk_fraction:
        return reject("full_premium_loss_exceeds_trade_budget")
    if account.open_option_debit + worst > account.equity * policy.max_total_option_debit_fraction:
        return reject("total_option_debit_exceeds_limit")
    if -account.daily_realized_pnl + worst >= account.peak_equity * policy.daily_loss_fraction:
        return reject("worst_case_trade_would_exhaust_daily_budget")
    return OptionDecision(True, "approved_for_paper_simulation_only", quantity, debit, worst, fees, spread, quote_id)
