from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from tradingbot.models import Instrument, Side
from tradingbot.research.orb15 import ORB15Config, ORBBar, run_orb15


TZ = ZoneInfo("America/Chicago")
MES = Instrument("MES", 0.25, 1.25, 5.0)


def _bar(stamp: datetime, *, open_=100.0, high=101.0, low=99.0,
         close=100.0, contract="MESZ26") -> ORBBar:
    return ORBBar(stamp, "MES", contract, open_, high, low, close, 100.0)


def _session(*, signal_close=101.25, entry_open=101.25, entry_high=104.0,
             entry_low=100.0, entry_contract="MESZ26", omit=()) -> list[ORBBar]:
    start = datetime(2026, 11, 9, 8, 30, tzinfo=TZ)
    bars = []
    for minute in range(15):
        stamp = start + timedelta(minutes=minute)
        if minute in omit:
            continue
        bars.append(_bar(stamp))
    signal_stamp = start + timedelta(minutes=15)
    if 15 not in omit:
        bars.append(_bar(signal_stamp, high=max(101.5, signal_close),
                         low=100.0, close=signal_close))
    entry_stamp = start + timedelta(minutes=16)
    if 16 not in omit:
        bars.append(_bar(entry_stamp, open_=entry_open, high=entry_high,
                         low=entry_low, close=entry_open, contract=entry_contract))
    return bars


def test_orb15_long_target_after_next_minute_entry_and_commission() -> None:
    result = run_orb15(_session(), MES, slippage_ticks_per_side=0)
    assert result.signals == 1
    assert result.accepted_entries == 1
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == Side.LONG
    assert trade.entry_time.time() == time(8, 46)
    assert trade.entry_price == pytest.approx(101.25)
    assert trade.stop_price == pytest.approx(98.75)
    assert trade.target_price == pytest.approx(103.75)
    assert trade.exit_reason == "TARGET"
    assert trade.exit_price == pytest.approx(103.75)
    assert trade.gross_pnl_usd == pytest.approx(12.5)
    assert trade.commission_usd == pytest.approx(1.14)
    assert trade.net_pnl_usd == pytest.approx(11.36)


def test_orb15_stop_wins_when_stop_and_target_touch_same_bar() -> None:
    bars = _session(entry_high=105.0, entry_low=98.0)
    result = run_orb15(bars, MES, slippage_ticks_per_side=0)
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "STOP"
    assert result.trades[0].exit_price == pytest.approx(98.75)
    assert result.trades[0].net_pnl_usd < 0


def test_orb15_gap_chase_cancels_entry_without_replacement() -> None:
    bars = _session(entry_open=102.25)
    result = run_orb15(bars, MES, slippage_ticks_per_side=0)
    assert result.signals == 1
    assert result.accepted_entries == 0
    assert result.cancelled_entries == 1
    assert dict(result.rejection_reasons)["gap_chase_filter"] == 1


def test_orb15_missing_opening_range_bar_invalidates_session() -> None:
    result = run_orb15(_session(omit=(7,)), MES, slippage_ticks_per_side=0)
    assert result.eligible_sessions == 0
    assert result.invalid_sessions == 1
    assert result.signals == 0
    assert dict(result.rejection_reasons)["incomplete_opening_range"] == 1


def test_orb15_same_contract_gap_forces_exit_at_next_valid_open() -> None:
    bars = _session()
    # Remove the minute immediately after entry, then provide a later same-contract bar.
    bars = [bar for bar in bars if bar.timestamp.time() != time(8, 47)]
    bars.append(_bar(datetime(2026, 11, 9, 8, 48, tzinfo=TZ),
                     open_=102.0, high=102.5, low=101.5, close=102.0))
    bars.sort(key=lambda item: item.timestamp)
    result = run_orb15(bars, MES, slippage_ticks_per_side=0)
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "DATA_GAP_FORCED_EXIT"
    assert result.trades[0].exit_price == pytest.approx(102.0)
    assert result.data_gap_forced_exits == 1


def test_orb15_contract_roll_while_position_open_is_unresolved_not_fabricated() -> None:
    bars = _session()
    bars.append(_bar(datetime(2026, 11, 9, 8, 47, tzinfo=TZ),
                     open_=102.0, high=102.5, low=101.5, close=102.0,
                     contract="MESU26"))
    bars.sort(key=lambda item: item.timestamp)
    result = run_orb15(bars, MES, slippage_ticks_per_side=0)
    assert result.trades == ()
    assert result.unresolved_positions == 1
    assert result.invalid_sessions == 1
    assert dict(result.rejection_reasons)["roll_or_session_boundary_in_position"] == 1


def test_orb15_time_exit_uses_exact_15_minute_endpoint() -> None:
    bars = _session(entry_high=102.0, entry_low=100.0)
    for minute in range(17, 31):
        stamp = datetime(2026, 11, 9, 8, 30, tzinfo=TZ) + timedelta(minutes=minute)
        bars.append(_bar(stamp, open_=101.25, high=102.0, low=100.5, close=101.5))
    bars.sort(key=lambda item: item.timestamp)
    result = run_orb15(bars, MES, slippage_ticks_per_side=0)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "TIME"
    assert trade.exit_time == datetime(2026, 11, 9, 9, 1, tzinfo=TZ)
    assert trade.bars_held == 15


def test_orb15_rejects_unsorted_duplicate_and_invalid_cost_inputs() -> None:
    bars = _session()
    with pytest.raises(ValueError, match="strictly chronological"):
        run_orb15(list(reversed(bars)), MES, slippage_ticks_per_side=0)
    with pytest.raises(ValueError, match="one of 0, 1 or 2"):
        run_orb15(bars, MES, slippage_ticks_per_side=3)
    with pytest.raises(ValueError, match="positive"):
        ORBBar(datetime(2026, 11, 9, 8, 30, tzinfo=TZ), "MES", "MESZ26",
               0, 1, -1, 0, 10)


def test_orb15_gap_inside_opening_range_invalidates_session() -> None:
    bars = _session(omit=(8,))
    result = run_orb15(bars, MES, slippage_ticks_per_side=0)
    assert result.eligible_sessions == 0
    assert result.invalid_sessions == 1
    assert dict(result.rejection_reasons)["incomplete_opening_range"] == 1


def test_orb15_short_trade_is_symmetric_and_uses_short_stop_target() -> None:
    start = datetime(2026, 11, 9, 8, 30, tzinfo=TZ)
    bars = [_bar(start + timedelta(minutes=i)) for i in range(15)]
    bars.append(_bar(start + timedelta(minutes=15), high=100.0, low=98.5, close=98.75))
    bars.append(_bar(start + timedelta(minutes=16), open_=98.75, high=99.0,
                     low=96.0, close=97.0))
    result = run_orb15(bars, MES, slippage_ticks_per_side=0)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == Side.SHORT
    assert trade.stop_price == pytest.approx(101.25)
    assert trade.target_price == pytest.approx(96.25)
    assert trade.exit_reason == "TARGET"
    assert trade.net_pnl_usd > 0


def test_orb15_slippage_stress_is_applied_to_both_entry_and_exit() -> None:
    bars = _session(entry_high=104.0, entry_low=98.0)
    zero = run_orb15(bars, MES, slippage_ticks_per_side=0).trades[0]
    one = run_orb15(bars, MES, slippage_ticks_per_side=1).trades[0]
    two = run_orb15(bars, MES, slippage_ticks_per_side=2).trades[0]
    assert zero.exit_reason == one.exit_reason == two.exit_reason == "STOP"
    assert zero.net_pnl_usd > one.net_pnl_usd > two.net_pnl_usd
    assert zero.slippage_usd == 0
    assert one.slippage_usd == pytest.approx(2.5)
    assert two.slippage_usd == pytest.approx(5.0)


def test_orb15_scorecard_labels_realized_drawdown_and_reports_costs() -> None:
    result = run_orb15(_session(), MES, slippage_ticks_per_side=0)
    metrics = result.metrics()
    assert metrics["trades"] == 1
    assert metrics["total_commission_usd"] == pytest.approx(1.14)
    assert metrics["total_slippage_usd"] == 0
    assert metrics["target_exits"] == 1
    assert metrics["closed_trade_max_drawdown_usd"] == 0
    assert "max_drawdown_usd" not in metrics
