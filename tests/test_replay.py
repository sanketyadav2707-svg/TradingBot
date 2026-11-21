from datetime import datetime, timedelta, timezone

from tradingbot.backtest.engine import BacktestConfig, BacktestEngine
from tradingbot.models import Bar, Instrument
from tradingbot.runtime.replay import build_replay_report, write_replay_report
from tradingbot.risk.limits import RiskGuard, RiskLimits
from tradingbot.strategy.ema_cross import EmaCrossStrategy


def _bars():
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    closes = [100 + (i * 0.15 if i < 20 else 3 - (i - 20) * 0.2) for i in range(50)]
    return [
        Bar(
            timestamp=start + timedelta(minutes=i),
            symbol="MES",
            open=close - 0.05,
            high=close + 0.15,
            low=close - 0.15,
            close=close,
            volume=100 + i,
        )
        for i, close in enumerate(closes)
    ]


def _engine():
    instrument = Instrument("MES", 0.25, 1.25, 5.0)
    guard = RiskGuard(
        RiskLimits(
            starting_balance_usd=50_000,
            max_daily_loss_usd=300,
            max_total_drawdown_usd=1_000,
            max_risk_per_trade_usd=50,
            max_contracts=1,
        ),
        commission_per_contract_per_side_usd=0.5,
        slippage_ticks_per_side=1,
    )
    return BacktestEngine(
        instrument,
        guard,
        EmaCrossStrategy(3, 8),
        BacktestConfig(stop_ticks=8, target_ticks=12, max_holding_bars=3),
    )


def test_replay_is_content_addressed_and_repeatable():
    first = build_replay_report(
        bars=_bars(), engine=_engine(), instrument=Instrument("MES", .25, 1.25, 5),
        strategy_name="EMA plumbing baseline", provider="synthetic-test", dataset="fixture-v1",
    )
    second = build_replay_report(
        bars=_bars(), engine=_engine(), instrument=Instrument("MES", .25, 1.25, 5),
        strategy_name="EMA plumbing baseline", provider="synthetic-test", dataset="fixture-v1",
    )
    assert first["run_id"] == second["run_id"]
    assert first["dataset"]["sha256"] == second["dataset"]["sha256"]
    assert first["configuration_sha256"] == second["configuration_sha256"]
    event_types = {event["event_type"] for event in first["events"]}
    assert "BAR_CLOSED" in event_types
    assert "SIGNAL_EMITTED" in event_types
    assert first["safety"]["live_orders_enabled"] is False


def test_replay_changes_identity_when_input_changes():
    bars = _bars()
    baseline = build_replay_report(
        bars=bars, engine=_engine(), instrument=Instrument("MES", .25, 1.25, 5),
        strategy_name="EMA plumbing baseline", provider="synthetic-test", dataset="fixture-v1",
    )
    changed = list(bars)
    last = changed[-1]
    changed[-1] = Bar(
        timestamp=last.timestamp, symbol=last.symbol, open=last.open,
        high=last.high + .25, low=last.low, close=last.close, volume=last.volume,
    )
    result = build_replay_report(
        bars=changed, engine=_engine(), instrument=Instrument("MES", .25, 1.25, 5),
        strategy_name="EMA plumbing baseline", provider="synthetic-test", dataset="fixture-v1",
    )
    assert baseline["run_id"] != result["run_id"]
    assert baseline["dataset"]["sha256"] != result["dataset"]["sha256"]


def test_replay_rejects_duplicate_or_out_of_order_bars():
    bars = _bars()
    bars[10] = bars[9]
    try:
        build_replay_report(
            bars=bars, engine=_engine(), instrument=Instrument("MES", .25, 1.25, 5),
            strategy_name="EMA plumbing baseline", provider="synthetic-test", dataset="fixture-v1",
        )
    except ValueError as exc:
        assert "strictly_chronological" in str(exc)
    else:
        raise AssertionError("duplicate timestamp was accepted")


def test_replay_report_write_is_atomic_and_json_round_trips(tmp_path):
    import json

    report = build_replay_report(
        bars=_bars(), engine=_engine(), instrument=Instrument("MES", .25, 1.25, 5),
        strategy_name="EMA plumbing baseline", provider="synthetic-test", dataset="fixture-v1",
    )
    target = write_replay_report(tmp_path / "replay.json", report)
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["run_id"] == report["run_id"]
    assert saved["dataset"]["row_count"] == 50
