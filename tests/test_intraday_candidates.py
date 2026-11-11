import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tradingbot.models import Instrument
from tradingbot.research.intraday_candidates import (
    CandidateConfig,
    run_candidate,
    run_candidate_matrix,
)
from tradingbot.research.orb15 import ORBBar
from tradingbot.cli import main


CT = ZoneInfo("America/Chicago")
MES = Instrument("MES", 0.25, 1.25, 5.0)


def make_bars(*, day=6, count=40, base=6000.0):
    start = datetime(2026, 4, day, 8, 30, tzinfo=CT)
    return [
        ORBBar(
            timestamp=start + timedelta(minutes=i),
            symbol="MES",
            contract_id="MESH6|123",
            open=base,
            high=base + 0.25,
            low=base - 0.25,
            close=base,
            volume=100,
        )
        for i in range(count)
    ]


def test_candidate_matrix_runs_both_strategies_under_same_cost_scenarios():
    bars = make_bars()
    matrix = run_candidate_matrix(bars, MES)
    assert set(matrix) == {
        "vwap_pullback_0tick", "vwap_pullback_1tick", "vwap_pullback_2tick",
        "compression_breakout_0tick", "compression_breakout_1tick", "compression_breakout_2tick",
    }
    for result in matrix.values():
        assert result.symbol == "MES"
        assert result.eligible_sessions == 1
        assert result.slippage_ticks_per_side in (0, 1, 2)
        assert result.metrics()["strategy"] in {"vwap_pullback", "compression_breakout"}


def test_candidates_do_not_create_signals_from_flat_market():
    bars = make_bars()
    for strategy in ("vwap_pullback", "compression_breakout"):
        result = run_candidate(
            bars, MES, strategy=strategy, slippage_ticks_per_side=1
        )
        assert result.signals == 0
        assert result.trades == ()


def test_candidate_rejects_data_gaps_and_contract_identity_changes():
    bars = make_bars()
    broken = list(bars)
    broken[20] = ORBBar(
        timestamp=broken[20].timestamp + timedelta(minutes=1),
        symbol="MES", contract_id="MESH6|123",
        open=6000, high=6000.25, low=5999.75, close=6000, volume=100,
    )
    result = run_candidate(
        broken, MES, strategy="compression_breakout", slippage_ticks_per_side=0
    )
    assert result.invalid_sessions == 1
    assert dict(result.rejection_reasons)["session_data_gap"] == 1

    rolled = list(bars)
    rolled[30] = ORBBar(
        timestamp=rolled[30].timestamp,
        symbol="MES", contract_id="MESM6|456",
        open=6000, high=6000.25, low=5999.75, close=6000, volume=100,
    )
    result = run_candidate(
        rolled, MES, strategy="vwap_pullback", slippage_ticks_per_side=0
    )
    assert result.invalid_sessions == 1
    assert dict(result.rejection_reasons)["contract_identity_change"] == 1


def test_candidate_rejects_invalid_strategy_and_cost():
    bars = make_bars()
    with pytest.raises(ValueError, match="strategy must be"):
        run_candidate(bars, MES, strategy="invented", slippage_ticks_per_side=0)
    with pytest.raises(ValueError, match="slippage_ticks_per_side"):
        run_candidate(bars, MES, strategy="vwap_pullback", slippage_ticks_per_side=3)


def test_config_rejects_invalid_compression_parameters():
    with pytest.raises(ValueError, match="compression_ratio"):
        CandidateConfig(compression_ratio=1.0)


def test_candidate_matrix_cli_writes_complete_exploratory_report(tmp_path, monkeypatch, capsys):
    import pyarrow as pa
    import pyarrow.parquet as pq

    source = tmp_path / "sample.parquet"
    start = datetime(2026, 4, 6, 9, 30)
    rows = []
    for i in range(40):
        stamp = start + timedelta(minutes=i)
        rows.append({
            "timestamp": stamp,
            "symbol": "MES",
            "asset_type": "Futures",
            "open": 6000.0,
            "high": 6000.25,
            "low": 5999.75,
            "close": 6000.0,
            "volume": 100.0,
        })
    pq.write_table(pa.Table.from_pylist(rows), source)
    calendar = tmp_path / "calendar.json"
    calendar.write_text(json.dumps({
        "calendar_name": "test",
        "timezone": "America/Chicago",
        "coverage_start": "2026-04-01",
        "coverage_end": "2026-04-30",
        "session_start": "17:00",
        "session_end": "16:00",
        "trade_weekdays": [0, 1, 2, 3, 4],
        "exceptions": [],
    }), encoding="utf-8")
    output = tmp_path / "candidate-report.json"
    monkeypatch.setattr(sys, "argv", [
        "tradingbot", "research-candidates-marketparquet",
        "--parquet", str(source),
        "--symbol", "MES",
        "--calendar", str(calendar),
        "--output", str(output),
    ])
    main()
    stdout = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert stdout["status"] == "exploratory_candidate_matrix_written"
    assert set(report["candidates"]) == {
        "vwap_pullback_0tick", "vwap_pullback_1tick", "vwap_pullback_2tick",
        "compression_breakout_0tick", "compression_breakout_1tick", "compression_breakout_2tick",
    }
    assert report["not_raw_contract_data"] is True
    assert report["research_mode"] == "EXPLORATORY_CONTINUOUS_FUTURES_ONLY"
