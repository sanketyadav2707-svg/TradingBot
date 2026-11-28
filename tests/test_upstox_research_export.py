from datetime import date, datetime, timedelta, timezone
import hashlib

import pytest

from tradingbot.data.upstox_chunk import HistoricalChunkError, persist_historical_chunk
from tradingbot.data.upstox_coverage import ChunkSource
from tradingbot.data.upstox_history import CandleRequestWindow
from tradingbot.data.upstox_research_export import export_upstox_research_csv
from tradingbot.research.nse import load_nse_bars_csv

KEY = "NSE_FO|fixture-only"
SYMBOL = "NIFTY26DEC_FUT"
T0 = datetime(2026, 11, 19, 3, 45, tzinfo=timezone.utc)
WINDOW = CandleRequestWindow(date(2026, 11, 1), date(2026, 11, 30))


def setup(tmp_path):
    source = tmp_path / "nov.json"
    payload = {"status": "success", "data": {"candles": [
        [(T0 + timedelta(minutes=i)).isoformat(), 100, 102, 99, 101, 200, 300]
        for i in (1, 0)
    ]}}
    persist_historical_chunk(payload, instrument_key=KEY, window=WINDOW, destination=source)
    return (ChunkSource(source, tmp_path / "nov.json.receipt.json", WINDOW),)


def export(tmp_path, chunks, timestamps):
    return export_upstox_research_csv(
        instrument_key=KEY, symbol=SYMBOL, contract_id="verified-contract-fixture",
        chunks=chunks, expected_timestamps=timestamps,
        licence_reference="fixture-license", calendar_reference="fixture-calendar",
        destination=tmp_path / "research.csv",
    )


def test_canonical_export_is_accepted_by_nse_research_loader(tmp_path):
    receipt = export(tmp_path, setup(tmp_path), (T0, T0 + timedelta(minutes=1)))
    target = tmp_path / "research.csv"
    assert hashlib.sha256(target.read_bytes()).hexdigest() == receipt.csv_sha256
    bars, provenance = load_nse_bars_csv(
        target, expected_symbol=SYMBOL, provider="upstox-fixture",
        dataset="test", licence_reference="fixture-license", retrieved_at=T0,
    )
    assert len(bars) == 2
    assert bars[0].contract_id == "verified-contract-fixture"
    assert bars[0].timestamp == T0
    assert receipt.bar_count == 2


def test_export_blocks_incomplete_calendar(tmp_path):
    with pytest.raises(HistoricalChunkError, match="incomplete"):
        export(tmp_path, setup(tmp_path), (T0,))


def test_export_never_overwrites_existing_dataset(tmp_path):
    chunks = setup(tmp_path)
    export(tmp_path, chunks, (T0, T0 + timedelta(minutes=1)))
    with pytest.raises(FileExistsError, match="immutable"):
        export(tmp_path, chunks, (T0, T0 + timedelta(minutes=1)))
