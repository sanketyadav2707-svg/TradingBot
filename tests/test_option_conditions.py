from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tradingbot.risk.option_conditions import (
    OptionConditionPolicy, OptionMarketConditions, reject_unsafe_option_conditions,
)
from tradingbot.risk.index_options import (
    OptionAccount, OptionContract, OptionQuote, OptionRiskPolicy, Right,
    evaluate_long_option_entry,
)

NOW = datetime(2026, 11, 23, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
D = Decimal


def healthy():
    return OptionMarketConditions(
        observed_at=NOW, event_calendar_checked_at=NOW - timedelta(hours=1),
        next_or_recent_high_impact_event_at=None,
        event_calendar_verified=True, market_state="normal",
        volatility_regime="normal", iv_change_5m_fraction=D("0.02"),
        underlying_move_1m_fraction=D("0.001"), round_trip_latency_ms=200,
        quote_feed_recovered=True, broker_session_healthy=True,
        exchange_order_eligibility_verified=True, consecutive_losses=0,
        last_loss_at=None,
    )


@pytest.mark.parametrize("change,reason", [
    ({"event_calendar_verified": False}, "high_impact_event_calendar_unverified"),
    ({"event_calendar_checked_at": NOW - timedelta(days=3)}, "stale_high_impact_event_calendar"),
    ({"market_state": "halted"}, "exchange_market_state_not_normal"),
    ({"volatility_regime": "extreme"}, "volatility_regime_unsafe_or_unknown"),
    ({"volatility_regime": "unknown"}, "volatility_regime_unsafe_or_unknown"),
    ({"iv_change_5m_fraction": D("-0.5")}, "implied_volatility_spike_or_crush"),
    ({"underlying_move_1m_fraction": D("0.02")}, "underlying_price_shock"),
    ({"round_trip_latency_ms": 2000}, "broker_latency_too_high"),
    ({"quote_feed_recovered": False}, "quote_feed_recovery_incomplete"),
    ({"broker_session_healthy": False}, "broker_session_unhealthy"),
    ({"exchange_order_eligibility_verified": False}, "exchange_order_eligibility_unverified"),
    ({"consecutive_losses": 2}, "consecutive_loss_circuit_breaker"),
    ({"last_loss_at": NOW - timedelta(minutes=5)}, "post_loss_cooldown_active"),
    ({"next_or_recent_high_impact_event_at": NOW + timedelta(minutes=5)}, "high_impact_event_blackout"),
    ({"next_or_recent_high_impact_event_at": NOW - timedelta(minutes=5)}, "high_impact_event_blackout"),
    ({"observed_at": NOW - timedelta(seconds=10)}, "stale_market_conditions"),
])
def test_conditions_fail_closed(change, reason):
    assert reject_unsafe_option_conditions(
        now=NOW, conditions=replace(healthy(), **change), policy=OptionConditionPolicy()
    ) == reason


def test_safe_conditions_pass_and_cooldown_expires():
    assert reject_unsafe_option_conditions(
        now=NOW, conditions=healthy(), policy=OptionConditionPolicy()
    ) is None
    assert reject_unsafe_option_conditions(
        now=NOW, conditions=replace(healthy(), last_loss_at=NOW-timedelta(minutes=25)),
        policy=OptionConditionPolicy(),
    ) is None


def test_conditions_integrate_with_option_entry():
    contract = OptionContract(
        instrument_key="NSE_FO|100", underlying="NIFTY", exchange="NSE",
        right=Right.CALL, strike=D("25000"), expiry=NOW.date() + timedelta(days=1),
        lot_size=65, tick_size=D("0.05"), quantity_freeze=1800,
        master_verified_at=NOW-timedelta(hours=1), master_source="https://www.nseindia.com",
    )
    quote = OptionQuote(
        timestamp=NOW, instrument_key=contract.instrument_key,
        bid=D("99"), ask=D("100"), bid_quantity=500, ask_quantity=500,
        underlying_price=D("25000"), underlying_timestamp=NOW,
        implied_volatility=D("0.2"), open_interest=2000,
    )
    account = OptionAccount(
        equity=D("1000000"), available_cash=D("1000000"), daily_realized_pnl=D("0"),
        peak_equity=D("1000000"), open_option_debit=D("0"), trades_today=0,
        open_positions=0, unresolved_orders=0, risk_halted=False, reconciled=True,
    )
    args=dict(now=NOW, contract=contract, quote=quote, account=account,
              policy=OptionRiskPolicy(), lots=1, round_trip_fees_rupees=D("60"),
              official_session_verified=True, data_feed_healthy=True,
              option_master_matches_quote=True, broker_permissions_verified=True,
              condition_policy=OptionConditionPolicy())
    assert evaluate_long_option_entry(**args, market_conditions=healthy()).approved
    rejected = evaluate_long_option_entry(
        **args, market_conditions=replace(healthy(), market_state="halted")
    )
    assert rejected.reason == "exchange_market_state_not_normal"
    assert evaluate_long_option_entry(**args).reason == "market_conditions_policy_incomplete"


def test_zero_bid_option_quote_is_valid_for_wipeout_simulation():
    quote = OptionQuote(
        timestamp=NOW, instrument_key="NSE_FO|100", bid=D("0"), ask=D("0.05"),
        bid_quantity=0, ask_quantity=65, underlying_price=D("25000"),
        underlying_timestamp=NOW, implied_volatility=D("0.2"), open_interest=500,
    )
    assert quote.bid == D("0")
