from datetime import datetime, timedelta, timezone

from tradingbot.models import Bar, Side, Signal
from tradingbot.runtime.strategy import (
    ClosedBarStrategyRuntime,
    MarketDataGate,
    RuntimeState,
    SignalValidator,
)


UTC = timezone.utc
T0 = datetime(2026, 11, 18, 4, 0, tzinfo=UTC)


def bar(minute=0, *, symbol="NIFTY26DEC_FUT"):
    price = 25000 + minute
    return Bar(
        timestamp=T0 + timedelta(minutes=minute),
        symbol=symbol,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price + .5,
        volume=100,
    )


def test_market_data_gate_rejects_stale_future_duplicate_and_wrong_symbol():
    gate = MarketDataGate(symbol="NIFTY26DEC_FUT", max_age_seconds=60)
    received = T0 + timedelta(minutes=1)
    assert gate.validate(bar(0), received_at=received).accepted
    assert gate.validate(bar(0), received_at=received).reason == "duplicate_or_out_of_order_market_bar"
    assert gate.validate(bar(2), received_at=received).reason == "future_dated_market_bar"
    assert gate.validate(bar(1, symbol="BANKNIFTY26DEC_FUT"), received_at=received).reason == "market_data_symbol_mismatch"
    assert gate.validate(bar(1), received_at=received + timedelta(minutes=2)).reason == "stale_market_bar"


def test_closed_bar_runtime_only_exposes_history_up_to_current_bar():
    observed = []
    dispatched = []

    def strategy(current, history):
        observed.append((current.timestamp, tuple(item.timestamp for item in history)))
        assert history[-1] is current
        assert all(item.timestamp <= current.timestamp for item in history)
        return Signal(Side.LONG, "test_signal") if current.timestamp == T0 else None

    runtime = ClosedBarStrategyRuntime(
        market_data_gate=MarketDataGate(symbol="NIFTY26DEC_FUT"),
        strategy_on_bar=strategy,
        on_signal=dispatched.append,
    )
    result = runtime.process_closed_bar(bar(0), received_at=T0 + timedelta(seconds=1))
    runtime.process_closed_bar(bar(1), received_at=T0 + timedelta(minutes=1, seconds=1))
    assert result is not None
    assert len(observed) == 2
    assert len(dispatched) == 1
    assert dispatched[0].signal_id == result.signal_id


def test_closed_bar_runtime_degrades_and_blocks_after_stale_data():
    calls = []
    runtime = ClosedBarStrategyRuntime(
        market_data_gate=MarketDataGate(symbol="NIFTY26DEC_FUT", max_age_seconds=30),
        strategy_on_bar=lambda current, history: calls.append(current) or None,
        on_signal=lambda signal: None,
    )
    assert runtime.process_closed_bar(
        bar(0), received_at=T0 + timedelta(seconds=1)
    ) is None
    assert runtime.process_closed_bar(
        bar(1), received_at=T0 + timedelta(minutes=2)
    ) is None
    assert runtime.state == RuntimeState.DEGRADED
    assert runtime.reason == "stale_market_bar"
    assert len(calls) == 1
    assert runtime.process_closed_bar(
        bar(2), received_at=T0 + timedelta(minutes=2)
    ) is None
    assert len(calls) == 1


def test_signal_validator_deduplicates_same_signal_but_allows_distinct_bar():
    validator = SignalValidator()
    first, reason = validator.validate(bar(0), Signal(Side.SHORT, "breakdown"))
    duplicate, duplicate_reason = validator.validate(bar(0), Signal(Side.SHORT, "breakdown"))
    next_bar, next_reason = validator.validate(bar(1), Signal(Side.SHORT, "breakdown"))
    assert first is not None and reason == "accepted"
    assert duplicate is None and duplicate_reason == "duplicate_signal"
    assert next_bar is not None and next_reason == "accepted"
    assert first.signal_id != next_bar.signal_id


def test_strategy_or_order_callback_exception_degrades_runtime():
    runtime = ClosedBarStrategyRuntime(
        market_data_gate=MarketDataGate(symbol="NIFTY26DEC_FUT"),
        strategy_on_bar=lambda current, history: Signal(Side.LONG, "go"),
        on_signal=lambda signal: (_ for _ in ()).throw(RuntimeError("router unavailable")),
    )
    assert runtime.process_closed_bar(
        bar(0), received_at=T0 + timedelta(seconds=1)
    ) is None
    assert runtime.state == RuntimeState.DEGRADED
    assert runtime.reason == "strategy_or_signal_handler_failed"


def test_runtime_halt_is_latched():
    runtime = ClosedBarStrategyRuntime(
        market_data_gate=MarketDataGate(symbol="NIFTY26DEC_FUT"),
        strategy_on_bar=lambda current, history: None,
        on_signal=lambda signal: None,
    )
    runtime.halt(reason="operator stop")
    assert runtime.state == RuntimeState.HALTED
    assert runtime.process_closed_bar(
        bar(0), received_at=T0 + timedelta(seconds=1)
    ) is None
