from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.accounting import PaperAccountEngine, PaperAccountStore
from tradingbot.data.closed_bar_inbox import ClosedBarInbox, MarketDataInboxBlocked
from tradingbot.models import Bar, Instrument, Side, Signal
from tradingbot.risk.limits import RiskLimits
from tradingbot.runtime.positions import PaperPositionManager, PaperTradingLoop
from tradingbot.runtime.strategy import ClosedBarStrategyRuntime, MarketDataGate
from tradingbot.runtime.paper_feed import PaperFeedRunner

UTC = timezone.utc
T0 = datetime(2026, 11, 19, 3, 45, tzinfo=UTC)
SYMBOL = "NIFTY26DEC_FUT"
INSTRUMENT = Instrument(
    SYMBOL, 0.05, 1.0, 20.0, currency_code="INR",
    lot_size=25, quantity_step=25, quantity_freeze=250,
)


def make_bar(minute):
    price = 25000.0 + minute
    if minute == 1:
        return Bar(T0 + timedelta(minutes=minute), SYMBOL, price, price + .5, price - .5, price + .25, 1000)
    return Bar(T0 + timedelta(minutes=minute), SYMBOL, price, price + 1, price - 1, price + .5, 1000)


def make_runner(tmp_path, *, max_age=60):
    store = PaperAccountStore(tmp_path / "runner.sqlite3", 100_000, currency_code="INR")
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
    router = engine.router_for(INSTRUMENT, require_firm_profile=False)
    runtime = ClosedBarStrategyRuntime(
        market_data_gate=MarketDataGate(
            symbol=SYMBOL, max_age_seconds=max_age, bar_interval_seconds=60
        ),
        strategy_on_bar=lambda current, history: (
            Signal(Side.LONG, "phase5_test") if len(history) == 1 else None
        ),
        on_signal=lambda signal: None,
    )
    manager = PaperPositionManager(
        engine, INSTRUMENT, stop_ticks=20, target_ticks=20, max_holding_bars=3
    )
    loop = PaperTradingLoop(strategy_runtime=runtime, position_manager=manager, router=router)
    inbox = ClosedBarInbox(store.path)
    return store, engine, runtime, manager, PaperFeedRunner(
        inbox=inbox, paper_loop=loop, expected_symbol=SYMBOL, source_id="fixture"
    )


def test_runner_durably_ingests_and_dispatches_to_phase4_paper_loop(tmp_path):
    store, engine, runtime, manager, runner = make_runner(tmp_path)
    runner.ingest(make_bar(0), received_at=T0 + timedelta(minutes=1, seconds=1))
    event = runner.drain_one()
    assert event is not None and event.status == "PROCESSED"
    assert runner.health().ready_for_dispatch
    assert runner.health().open_positions == 0
    runner.ingest(make_bar(1), received_at=T0 + timedelta(minutes=2, seconds=1))
    runner.drain_one()
    assert store.get_summary()["fills_count"] == 1
    assert runner.health().open_positions == 1
    assert not engine.halted


def test_runner_rejects_wrong_symbol_before_durable_enqueue(tmp_path):
    _, _, _, _, runner = make_runner(tmp_path)
    wrong = Bar(T0, "BANKNIFTY26DEC_FUT", 25000, 25001, 24999, 25000, 100)
    with pytest.raises(ValueError, match="symbol"):
        runner.ingest(wrong, received_at=T0 + timedelta(minutes=1))
    assert runner.inbox.health().pending == 0


def test_stale_market_bar_latches_failed_inbox_and_stops_future_dispatch(tmp_path):
    _, _, runtime, manager, runner = make_runner(tmp_path, max_age=10)
    runner.ingest(make_bar(0), received_at=T0 + timedelta(minutes=2))
    with pytest.raises(RuntimeError, match="runtime_not_running"):
        runner.drain_one()
    assert runtime.state.value == "DEGRADED"
    assert runner.inbox.health().failed == 1
    assert not runner.health().ready_for_dispatch
    with pytest.raises(MarketDataInboxBlocked):
        runner.drain_one()


def test_runner_health_blocks_unresolved_order_and_halted_account(tmp_path):
    _, engine, _, _, runner = make_runner(tmp_path)
    engine.emergency_halt("operator test")
    assert not runner.health().ready_for_dispatch
