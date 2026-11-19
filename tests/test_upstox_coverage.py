from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradingbot.data.upstox_chunk import HistoricalChunkError, persist_historical_chunk
from tradingbot.data.upstox_history import CandleRequestWindow
from tradingbot.data.upstox_coverage import ChunkSource, audit_historical_coverage

KEY = "NSE_FO|fixture-only"
WINDOW = CandleRequestWindow(date(2026, 11, 1), date(2026, 11, 30))
T0 = datetime(2026, 11, 19, 3, 45, tzinfo=timezone.utc)


def payload(minutes=(0, 1)):
    return {"status": "success", "data": {"candles": [
        [(T0 + timedelta(minutes=i)).isoformat(), 100, 102, 99, 101, 200, 300]
        for i in sorted(minutes, reverse=True)
    ]}}


def fixture(tmp_path, minutes=(0, 1)):
    target = tmp_path / "nov.json"
    persist_historical_chunk(payload(minutes), instrument_key=KEY, window=WINDOW, destination=target)
    return ChunkSource(target, tmp_path / "nov.json.receipt.json", WINDOW)


def test_exact_coverage_passes_only_against_explicit_calendar(tmp_path):
    source = fixture(tmp_path)
    result = audit_historical_coverage(
        instrument_key=KEY, chunks=(source,),
        expected_timestamps=(T0, T0 + timedelta(minutes=1)),
    )
    assert result.complete
    assert result.observed_bars == result.expected_bars == 2


def test_missing_bar_fails_coverage(tmp_path):
    source = fixture(tmp_path, (0,))
    result = audit_historical_coverage(
        instrument_key=KEY, chunks=(source,),
        expected_timestamps=(T0, T0 + timedelta(minutes=1)),
    )
    assert not result.complete
    assert len(result.missing_timestamps) == 1


def test_unexpected_bar_fails_coverage(tmp_path):
    source = fixture(tmp_path)
    result = audit_historical_coverage(
        instrument_key=KEY, chunks=(source,),
        expected_timestamps=(T0,),
    )
    assert not result.complete
    assert len(result.unexpected_timestamps) == 1


def test_modified_chunk_rejected_even_if_still_valid_json(tmp_path):
    source = fixture(tmp_path)
    source.path.write_text(source.path.read_text() + " ")
    with pytest.raises(HistoricalChunkError, match="checksum"):
        audit_historical_coverage(
            instrument_key=KEY, chunks=(source,),
            expected_timestamps=(T0, T0 + timedelta(minutes=1)),
        )


def test_wrong_instrument_and_missing_calendar_rejected(tmp_path):
    source = fixture(tmp_path)
    with pytest.raises(HistoricalChunkError, match="instrument"):
        audit_historical_coverage(
            instrument_key="NSE_FO|different", chunks=(source,), expected_timestamps=(T0,),
        )
    with pytest.raises(HistoricalChunkError, match="calendar"):
        audit_historical_coverage(
            instrument_key=KEY, chunks=(source,), expected_timestamps=(),
        )


def test_duplicate_expected_timestamp_rejected(tmp_path):
    source = fixture(tmp_path)
    with pytest.raises(HistoricalChunkError, match="duplicate_expected"):
        audit_historical_coverage(
            instrument_key=KEY, chunks=(source,), expected_timestamps=(T0, T0),
        )
