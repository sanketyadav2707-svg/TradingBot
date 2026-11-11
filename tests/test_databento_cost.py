from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from tradingbot.data.databento_cost import estimate_databento_historical_cost, write_cost_estimate


def test_cost_estimator_is_metadata_only_and_aggregates_roots(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-only")
    calls = []

    class Metadata:
        def get_cost(self, **kwargs):
            calls.append(kwargs)
            return {"MES.FUT": 1.25, "MNQ.FUT": 2.5}[kwargs["symbols"][0]]

    class Historical:
        def __init__(self, key):
            assert key == "test-only"
            self.metadata = Metadata()

            def forbidden(*args, **kwargs):
                raise AssertionError("A cost preflight must never download data")

            self.timeseries = SimpleNamespace(get_range=forbidden)

    monkeypatch.setitem(sys.modules, "databento", SimpleNamespace(Historical=Historical))
    report = estimate_databento_historical_cost(
        start="2026-01-01T00:00:00Z",
        end="2026-04-01T00:00:00Z",
    )
    assert report["status"] == "estimate_only_no_data_requested"
    assert report["estimated_total_usd"] == pytest.approx(3.75)
    assert [call["symbols"] for call in calls] == [["MES.FUT"], ["MNQ.FUT"]]
    assert all(call["stype_in"] == "parent" for call in calls)
    assert all(call["schema"] == "ohlcv-1m" for call in calls)


def test_cost_estimator_requires_key_and_aware_ordered_dates(monkeypatch) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DATABENTO_API_KEY"):
        estimate_databento_historical_cost(
            start="2026-01-01T00:00:00Z", end="2026-02-01T00:00:00Z"
        )

    monkeypatch.setenv("DATABENTO_API_KEY", "test-only")
    with pytest.raises(ValueError, match="explicit timezone"):
        estimate_databento_historical_cost(
            start="2026-01-01T00:00:00", end="2026-02-01T00:00:00Z"
        )
    with pytest.raises(ValueError, match="earlier"):
        estimate_databento_historical_cost(
            start="2026-02-01T00:00:00Z", end="2026-01-01T00:00:00Z"
        )


def test_cost_estimator_rejects_invalid_symbol(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-only")
    with pytest.raises(ValueError, match="MES, MNQ"):
        estimate_databento_historical_cost(
            symbols=("ES",),
            start="2026-01-01T00:00:00Z",
            end="2026-02-01T00:00:00Z",
        )


def test_cost_report_writer_creates_parent_directory(tmp_path) -> None:
    target = write_cost_estimate(tmp_path / "nested" / "estimate.json", {"estimated_total_usd": 0})
    assert target.is_file()
    assert '"estimated_total_usd": 0' in target.read_text()
