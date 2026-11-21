from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tradingbot.paper.index_options import LongOptionPaperSimulator
from tradingbot.risk.index_options import (
    OptionAccount, OptionContract, OptionQuote, OptionRiskPolicy,
    Right, evaluate_long_option_entry,
)

D = Decimal
IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=IST)


def setup():
    contract = OptionContract(
        instrument_key="NSE_FO|100", underlying="NIFTY", exchange="NSE",
        right=Right.CALL, strike=D("25000"), expiry=date(2026, 11, 24),
        lot_size=65, tick_size=D("0.05"), quantity_freeze=1800,
        master_verified_at=NOW - timedelta(hours=1),
        master_source="https://www.nseindia.com",
    )
    quote = OptionQuote(
        timestamp=NOW, instrument_key=contract.instrument_key,
        bid=D("99"), ask=D("100"), bid_quantity=200, ask_quantity=200,
        underlying_price=D("25000"), underlying_timestamp=NOW,
        implied_volatility=D("0.25"), open_interest=1000,
    )
    account = OptionAccount(
        equity=D("1000000"), available_cash=D("100000"), daily_realized_pnl=D("0"),
        peak_equity=D("1000000"), open_option_debit=D("0"), trades_today=0,
        open_positions=0, unresolved_orders=0, risk_halted=False, reconciled=True,
    )
    decision = evaluate_long_option_entry(
        now=NOW, contract=contract, quote=quote, account=account,
        policy=OptionRiskPolicy(), lots=1, round_trip_fees_rupees=D("60"),
        official_session_verified=True, data_feed_healthy=True,
        option_master_matches_quote=True, broker_permissions_verified=True,
    )
    assert decision.approved
    sim = LongOptionPaperSimulator()
    sim.enter(decision=decision, contract=contract, quote=quote)
    return sim, quote


def test_paper_entry_uses_ask_and_profitable_exit_uses_bid_only():
    sim, quote = setup()
    updated = replace(quote, timestamp=NOW + timedelta(seconds=3),
                      bid=D("131"), ask=D("132"))
    exit_event = sim.evaluate_exit(quote=updated, now=updated.timestamp,
                                   extra_exit_slippage=D("1"))
    assert exit_event.reason == "TAKE_PROFIT_SIGNAL"
    assert exit_event.executable_bid == D("130")
    assert exit_event.net_pnl == D("1890")
    assert sim.position is None


def test_stop_signal_can_realize_more_loss_than_stop_threshold():
    sim, quote = setup()
    crash_quote = replace(quote, timestamp=NOW + timedelta(seconds=3),
                          bid=D("50"), ask=D("60"))
    exit_event = sim.evaluate_exit(quote=crash_quote, now=crash_quote.timestamp)
    assert exit_event.reason == "STOP_SIGNAL"
    assert exit_event.net_pnl == D("-3310")
    assert exit_event.net_pnl < -(D("15") * D("65"))
    assert sim.realized_pnl == exit_event.net_pnl


def test_paper_time_exit_and_insufficient_depth_halts_open_position():
    sim, quote = setup()
    after = replace(quote, timestamp=NOW + timedelta(minutes=15),
                    bid=D("95"), ask=D("96"), bid_quantity=1)
    with pytest.raises(RuntimeError, match="exit_depth"):
        sim.evaluate_exit(quote=after, now=after.timestamp)
    assert sim.halted
    assert sim.position is not None
    with pytest.raises(RuntimeError, match="halted"):
        sim.evaluate_exit(quote=after, now=after.timestamp)


def test_stale_exit_quote_halts_instead_of_fabricating_fill():
    sim, quote = setup()
    with pytest.raises(RuntimeError, match="unreliable"):
        sim.evaluate_exit(quote=quote, now=NOW + timedelta(minutes=15))
    assert sim.position is not None


def test_duplicate_entry_rejected():
    sim, quote = setup()
    from tradingbot.risk.index_options import OptionDecision
    decision = OptionDecision(True, "test", 65, D("6500"), D("6560"), D("60"), D("0.01"))
    with pytest.raises(RuntimeError, match="simultaneous"):
        sim.enter(decision=decision, contract=OptionContract(
            instrument_key="NSE_FO|100", underlying="NIFTY", exchange="NSE",
            right=Right.CALL, strike=D("25000"), expiry=date(2026, 11, 24),
            lot_size=65, tick_size=D("0.05"), quantity_freeze=1800,
            master_verified_at=NOW, master_source="https://www.nseindia.com",
        ), quote=quote)


def test_paper_time_exit_without_stop_or_target():
    sim, quote = setup()
    exit_quote = replace(quote, timestamp=NOW + timedelta(minutes=15),
                         bid=D("99"), ask=D("100"))
    event = sim.evaluate_exit(quote=exit_quote, now=exit_quote.timestamp)
    assert event.reason == "TIME_EXIT_SIGNAL"
    assert event.net_pnl == D("-125")


def test_paper_engine_rejects_unsafe_holding_window():
    with pytest.raises(ValueError, match="3_to_15"):
        LongOptionPaperSimulator(max_holding_seconds=60)
