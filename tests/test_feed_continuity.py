from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.data.continuity import ClosedBarContinuityGuard
from tradingbot.models import Bar

T0 = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)


def bar(minute, symbol="NIFTY26DEC_FUT"):
    return Bar(T0 + timedelta(minutes=minute), symbol, 25000, 25001, 24999, 25000.5, 100)


def test_contiguous_bars_pass():
    guard = ClosedBarContinuityGuard(symbol="NIFTY26DEC_FUT")
    assert guard.inspect(bar(0)).accepted
    assert guard.inspect(bar(1)).accepted
    assert guard.last_timestamp == T0 + timedelta(minutes=1)


def test_missing_candle_halts_and_does_not_silently_resynchronize():
    guard = ClosedBarContinuityGuard(symbol="NIFTY26DEC_FUT")
    guard.inspect(bar(0))
    result = guard.inspect(bar(2))
    assert not result.accepted
    assert result.reason == "missing_bar_gap"
    assert result.expected_timestamp == T0 + timedelta(minutes=1)
    assert not guard.inspect(bar(1)).accepted
    assert guard.halted


def test_duplicate_and_symbol_mismatch_halt():
    guard = ClosedBarContinuityGuard(symbol="NIFTY26DEC_FUT")
    guard.inspect(bar(0))
    assert guard.inspect(bar(0)).reason == "duplicate_or_out_of_order_bar"
    other = ClosedBarContinuityGuard(symbol="NIFTY26DEC_FUT")
    assert other.inspect(bar(0, "BANKNIFTY26DEC_FUT")).reason == "symbol_mismatch"


def test_reset_requires_explicit_flat_and_reconciliation():
    guard = ClosedBarContinuityGuard(symbol="NIFTY26DEC_FUT")
    guard.inspect(bar(0))
    guard.inspect(bar(2))
    with pytest.raises(RuntimeError, match="flat_reconciled"):
        guard.reset_for_new_session(flat=True, reconciled=False)
    guard.reset_for_new_session(flat=True, reconciled=True)
    assert not guard.halted
    assert guard.inspect(bar(5)).accepted


def test_rejects_invalid_interval():
    with pytest.raises(ValueError, match="interval"):
        ClosedBarContinuityGuard(symbol="NIFTY26DEC_FUT", interval_seconds=0)
