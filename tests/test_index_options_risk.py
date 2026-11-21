from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tradingbot.risk.index_options import (
    OptionAccount,
    OptionContract,
    OptionQuote,
    OptionRiskPolicy,
    Right,
    evaluate_long_option_entry,
)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=IST)
D = Decimal


def fixture():
    contract = OptionContract(
        instrument_key="NSE_FO|123456",
        underlying="NIFTY",
        exchange="NSE",
        right=Right.CALL,
        strike=D("25000"),
        expiry=date(2026, 11, 24),
        lot_size=65,
        tick_size=D("0.05"),
        quantity_freeze=1800,
        master_verified_at=NOW - timedelta(hours=2),
        master_source="https://www.nseindia.com",
    )
    quote = OptionQuote(
        timestamp=NOW - timedelta(seconds=1),
        bid=D("99.00"),
        ask=D("100.00"),
        bid_quantity=1000,
        ask_quantity=1000,
        underlying_price=D("25010"),
        underlying_timestamp=NOW - timedelta(seconds=1),
        implied_volatility=D("0.20"),
        open_interest=15000,
    )
    account = OptionAccount(
        equity=D("1000000"),
        available_cash=D("500000"),
        daily_realized_pnl=D("0"),
        peak_equity=D("1000000"),
        open_option_debit=D("0"),
        trades_today=0,
        open_positions=0,
        unresolved_orders=0,
        risk_halted=False,
        reconciled=True,
    )
    return contract, quote, account, OptionRiskPolicy()


def decision(**changes):
    contract, quote, account, policy = fixture()
    values = dict(
        now=NOW,
        contract=contract,
        quote=quote,
        account=account,
        policy=policy,
        lots=1,
        round_trip_fees_rupees=D("60"),
        official_session_verified=True,
        data_feed_healthy=True,
        option_master_matches_quote=True,
        broker_permissions_verified=True,
    )
    values.update(changes)
    return evaluate_long_option_entry(**values)


def test_healthy_one_lot_paper_entry_exposes_full_debit():
    result = decision()
    assert result.approved
    assert result.quantity == 65
    assert result.debit_rupees == D("6500")
    assert result.worst_case_loss_rupees == D("6560")
    assert result.reason == "approved_for_paper_simulation_only"


def test_twenty_thousand_capital_rejects_one_lot_instead_of_reducing_exchange_lot():
    _, _, account, _ = fixture()
    account = replace(account, equity=D("20000"), peak_equity=D("20000"),
                      available_cash=D("20000"))
    result = decision(account=account)
    assert not result.approved
    assert result.quantity == 0
    assert result.reason == "full_premium_loss_exceeds_trade_budget"


@pytest.mark.parametrize("changes,reason", [
    ({"official_session_verified": False}, "exchange_session_unverified"),
    ({"data_feed_healthy": False}, "market_feed_unhealthy"),
    ({"option_master_matches_quote": False}, "option_contract_not_reconciled"),
    ({"broker_permissions_verified": False}, "broker_permissions_unverified"),
    ({"now": NOW + timedelta(minutes=10)}, "option_quote_stale"),
    ({"now": NOW - timedelta(seconds=3)}, "future_dated_market_quote"),
    ({"lots": 30}, "exchange_quantity_freeze_exceeded"),
])
def test_missing_evidence_and_market_data_fail_closed(changes, reason):
    assert decision(**changes).reason == reason


def test_wide_spread_thin_depth_and_iv_spike_rejected():
    _, q, _, _ = fixture()
    assert decision(quote=replace(q, bid=D("90"))).reason == "bid_ask_spread_too_wide"
    assert decision(quote=replace(q, ask_quantity=1)).reason == "insufficient_top_of_book_depth"
    assert decision(quote=replace(q, implied_volatility=D("2"))).reason == "implied_volatility_above_limit"
    assert decision(quote=replace(q, trading_halted=True)).reason == "market_halt_active"


def test_account_halt_open_position_unreconciled_orders_and_drawdown_block():
    _, _, a, _ = fixture()
    assert decision(account=replace(a, risk_halted=True)).reason == "account_halted_unreconciled_or_orders_unresolved"
    assert decision(account=replace(a, unresolved_orders=1)).reason == "account_halted_unreconciled_or_orders_unresolved"
    assert decision(account=replace(a, open_positions=1)).reason == "simultaneous_option_positions_disabled"
    assert decision(account=replace(a, equity=D("900000"))).reason == "equity_drawdown_limit_reached"


def test_wrong_expiry_and_missing_funds_fail_closed():
    c, _, a, _ = fixture()
    assert decision(contract=replace(c, expiry=NOW.date())).reason == "expiry_risk_outside_policy"
    assert decision(account=replace(a, available_cash=D("1000"))).reason == "insufficient_cash_for_full_debit"


def test_rejects_float_money_nan_and_unverified_broker_flags():
    c, q, a, policy = fixture()
    with pytest.raises(ValueError, match="exact_decimal"):
        OptionQuote(
            timestamp=NOW, bid=99.0, ask=D("100"), bid_quantity=65,
            ask_quantity=65, underlying_price=D("25000"),
            underlying_timestamp=NOW, implied_volatility=D("0.2"),
            open_interest=1000,
        )
    with pytest.raises(ValueError, match="finite"):
        decision(round_trip_fees_rupees=D("NaN"))
    with pytest.raises(TypeError, match="booleans"):
        decision(broker_permissions_verified=1)


def test_fee_budget_and_market_risk_not_confused_with_guaranteed_stop():
    c, q, a, p = fixture()
    result = decision(round_trip_fees_rupees=D("19000"))
    assert not result.approved
    assert result.worst_case_loss_rupees == D("25500")
    assert result.reason == "full_premium_loss_exceeds_trade_budget"
