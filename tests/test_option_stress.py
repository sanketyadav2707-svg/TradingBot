from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tradingbot.risk.index_options import (
    OptionAccount, OptionContract, OptionQuote, OptionRiskPolicy,
    Right, evaluate_long_option_entry,
)
from tradingbot.risk.option_stress import OptionShock, stress_test_long_option

D = Decimal
IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=IST)


def approved():
    contract = OptionContract(
        instrument_key="NSE_FO|100", underlying="NIFTY", exchange="NSE",
        right=Right.CALL, strike=D("25000"), expiry=date(2026, 11, 24),
        lot_size=65, tick_size=D("0.05"), quantity_freeze=1800,
        master_verified_at=NOW - timedelta(hours=1),
        master_source="https://www.nseindia.com",
    )
    quote = OptionQuote(
        timestamp=NOW - timedelta(seconds=1),
        instrument_key="NSE_FO|100",
        bid=D("99"), ask=D("100"), bid_quantity=200, ask_quantity=200,
        underlying_price=D("25000"), underlying_timestamp=NOW - timedelta(seconds=1),
        implied_volatility=D("0.25"), open_interest=1000,
    )
    account = OptionAccount(
        equity=D("1000000"), available_cash=D("100000"), daily_realized_pnl=D("0"),
        peak_equity=D("1000000"), open_option_debit=D("0"), trades_today=0,
        open_positions=0, unresolved_orders=0, risk_halted=False, reconciled=True,
    )
    result = evaluate_long_option_entry(
        now=NOW, contract=contract, quote=quote, account=account,
        policy=OptionRiskPolicy(), lots=1, round_trip_fees_rupees=D("60"),
        official_session_verified=True, data_feed_healthy=True,
        option_master_matches_quote=True, broker_permissions_verified=True,
    )
    assert result.approved
    return result


def test_wipeout_iv_crush_and_spread_stress():
    report = stress_test_long_option(
        entry_decision=approved(), equity=D("1000000"),
        shocks=(
            OptionShock("premium_to_zero", D("0")),
            OptionShock("iv_crush", D("50")),
            OptionShock("wide_exit_spread", D("80"), D("10"), D("20")),
            OptionShock("directional_win", D("120")),
        ),
    )
    assert report.entry_debit == D("6500")
    assert report.break_even_exit_bid == (D("6560") / D("65"))
    assert report.worst_modeled_loss == D("-6560")
    assert report.scenarios[0].loss_fraction_of_equity == D("0.00656")
    assert report.scenarios[1].net_pnl_rupees == D("-3310")
    assert report.scenarios[2].net_pnl_rupees == D("-2030")
    assert report.scenarios[3].profitable


def test_slippage_cannot_make_option_sale_price_negative():
    report = stress_test_long_option(
        entry_decision=approved(), equity=D("1000000"),
        shocks=(OptionShock("illiquid", D("1"), D("100")),),
    )
    assert report.scenarios[0].final_exit_bid == D("0")


def test_invalid_shock_or_unapproved_entry_rejected():
    with pytest.raises(ValueError, match="nonnegative"):
        OptionShock("invalid", D("-1"))
    with pytest.raises(ValueError, match="shocks"):
        stress_test_long_option(entry_decision=approved(), equity=D("1000000"), shocks=())
