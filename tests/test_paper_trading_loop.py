from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import sqlite3

from tradingbot.accounting import PaperAccountEngine, PaperAccountStore
from tradingbot.models import Bar, Instrument, Side, Signal
from tradingbot.risk.limits import RiskLimits
from tradingbot.runtime.positions import PaperPositionManager, PaperTradingLoop, PositionExit
from tradingbot.runtime.strategy import ClosedBarStrategyRuntime, MarketDataGate, RuntimeState


TZ = ZoneInfo("Asia/Kolkata")
START = datetime(2026, 11, 18, 9, 15, tzinfo=TZ)
NIFTY = Instrument(
    "NIFTY26DEC_FUT", 0.05, 1.0, 20.0,
    currency_code="INR", lot_size=25, quantity_step=25, quantity_freeze=250,
)


def make_bar(minute, *, open_, high, low, close):
    return Bar(
        timestamp=START + timedelta(minutes=minute),
        symbol=NIFTY.symbol,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000,
    )


def make_runtime_and_loop(tmp_path, *, stop_ticks=4, target_ticks=8, max_holding_bars=3):
    store = PaperAccountStore(tmp_path / "paper-loop.sqlite3", 100_000, currency_code="INR")
    engine = PaperAccountEngine(
        store,
        RiskLimits(
            starting_balance_usd=100_000,
            max_daily_loss_usd=1_000,
            max_total_drawdown_usd=5_000,
            max_risk_per_trade_usd=1_000,
            max_contracts=1,
            currency_code="INR",
        ),
        slippage_ticks_per_side=0,
        risk_timezone="Asia/Kolkata",
    )
    router = engine.router_for(NIFTY, require_firm_profile=False)
    runtime = ClosedBarStrategyRuntime(
        market_data_gate=MarketDataGate(
            symbol=NIFTY.symbol,
            max_age_seconds=60,
            bar_interval_seconds=60,
        ),
        strategy_on_bar=lambda current, history: (
            Signal(Side.LONG, "opening_range_break") if len(history) == 1 else None
        ),
        on_signal=lambda signal: None,
    )
    manager = PaperPositionManager(
        engine,
        NIFTY,
        stop_ticks=stop_ticks,
        target_ticks=target_ticks,
        max_holding_bars=max_holding_bars,
        bar_interval_seconds=60,
    )
    return store, engine, runtime, manager, PaperTradingLoop(
        strategy_runtime=runtime,
        position_manager=manager,
        router=router,
    )


def process(loop, bar):
    return loop.process_closed_bar(
        bar, received_at=bar.timestamp + timedelta(seconds=61)
    )


def test_paper_loop_queues_signal_then_fills_at_next_bar_open_and_takes_profit(tmp_path):
    store, engine, runtime, manager, loop = make_runtime_and_loop(tmp_path)
    first = make_bar(0, open_=25000, high=25001, low=24999, close=25000.5)
    second = make_bar(1, open_=25001, high=25002, low=25001, close=25001.5)

    signal = process(loop, first)
    assert signal is not None
    assert signal.timestamp == START + timedelta(minutes=1)
    assert loop.pending_signal is not None
    assert store.get_summary()["fills_count"] == 0

    exit_event = process(loop, second)
    assert isinstance(exit_event, PositionExit)
    assert exit_event.reason == "TAKE_PROFIT"
    assert exit_event.reference_price == Decimal("25001.4")
    fills = store.list_fills()
    assert len(fills) == 2
    assert float(fills[0]["requested_price"]) == 25001.0
    assert store.list_positions() == []
    assert len(store.list_trades()) == 1
    assert not manager.has_position
    assert engine.store.get_summary()["open_positions"] == 0


def test_paper_position_manager_uses_stop_first_when_stop_and_target_both_touch(tmp_path):
    store, engine, runtime, manager, loop = make_runtime_and_loop(tmp_path)
    process(loop, make_bar(0, open_=25000, high=25001, low=24999, close=25000.5))
    result = process(
        loop,
        make_bar(1, open_=25001, high=25002, low=25000.5, close=25001.5),
    )
    assert isinstance(result, PositionExit)
    assert result.reason == "STOP_LOSS"
    assert result.reference_price == Decimal("25000.8")
    assert store.list_positions() == []


def test_paper_position_manager_enforces_maximum_holding_bars(tmp_path):
    store, engine, runtime, manager, loop = make_runtime_and_loop(
        tmp_path, stop_ticks=20, target_ticks=20, max_holding_bars=1
    )
    process(loop, make_bar(0, open_=25000, high=25001, low=24999, close=25000.5))
    result = process(
        loop,
        make_bar(1, open_=25001, high=25001.2, low=25000.9, close=25001.1),
    )
    assert isinstance(result, PositionExit)
    assert result.reason == "TIME_EXIT"
    assert result.reference_price == Decimal("25001.1")
    assert result.bars_held == 1
    assert store.list_positions() == []


def test_position_manager_recovers_persisted_stop_target_and_bar_cursor(tmp_path):
    store, engine, runtime, manager, loop = make_runtime_and_loop(tmp_path)
    process(loop, make_bar(0, open_=25000, high=25001, low=24999, close=25000.5))
    entry = process(
        loop,
        make_bar(1, open_=25001, high=25001.2, low=25000.9, close=25001.1),
    )
    assert entry is not None
    assert manager.has_position

    recovered = PaperPositionManager(
        engine, NIFTY, stop_ticks=1, target_ticks=1, max_holding_bars=1
    )
    assert recovered.has_position
    assert recovered.stop_ticks == 4
    assert recovered.target_ticks == 8
    assert recovered.max_holding_bars == 3
    exit_event = recovered.on_closed_bar(
        make_bar(2, open_=25001.1, high=25001.6, low=25001.0, close=25001.5)
    )
    assert isinstance(exit_event, PositionExit)
    assert exit_event.reason == "TAKE_PROFIT"
    assert store.list_positions() == []


def test_missing_position_manager_state_halts_but_operator_can_flatten(tmp_path):
    store, engine, runtime, manager, loop = make_runtime_and_loop(tmp_path)
    process(loop, make_bar(0, open_=25000, high=25001, low=24999, close=25000.5))
    process(loop, make_bar(1, open_=25001, high=25001.2, low=25000.9, close=25001.1))
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "DELETE FROM paper_position_manager_state WHERE symbol = ?",
            (NIFTY.symbol,),
        )

    recovered = PaperPositionManager(
        engine, NIFTY, stop_ticks=4, target_ticks=8, max_holding_bars=3
    )
    assert recovered.halted
    assert engine.halted
    result = recovered.force_flatten(
        reference_price=25001.0,
        timestamp=START + timedelta(minutes=3),
        reason="OPERATOR_RECOVERY_FLATTEN",
    )
    assert isinstance(result, PositionExit)
    assert store.list_positions() == []
    assert engine.halted


def test_paper_loop_rejects_holding_period_over_fifteen_minutes(tmp_path):
    store = PaperAccountStore(tmp_path / "limit.sqlite3", 100_000, currency_code="INR")
    engine = PaperAccountEngine(store, RiskLimits(currency_code="INR"))
    import pytest

    with pytest.raises(ValueError, match="holding_limit_exceeds_15_minutes"):
        PaperPositionManager(
            engine, NIFTY, stop_ticks=4, target_ticks=8,
            max_holding_bars=16, bar_interval_seconds=60,
        )
