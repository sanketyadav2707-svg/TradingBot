from datetime import date
import json

import pytest

from tradingbot.data.upstox_history import CandleRequestWindow
from tradingbot.data.upstox_chunk import HistoricalChunkError, persist_historical_chunk, validate_historical_chunk

WINDOW = CandleRequestWindow(date(2026, 11, 1), date(2026, 11, 30))
KEY = "NSE_FO|fixture-only"


def payload():
    return {"status": "success", "data": {"candles": [
        ["2026-11-19T09:16:00+05:30", 100, 102, 99, 101, 200, 300],
        ["2026-11-19T09:15:00+05:30", 100, 101, 99, 100, 100, 250],
    ]}}


def test_chunk_validation_and_immutable_capture(tmp_path):
    stamps, raw = validate_historical_chunk(payload(), instrument_key=KEY, window=WINDOW)
    assert len(stamps) == 2
    target = tmp_path / "chunk.json"
    receipt = persist_historical_chunk(payload(), instrument_key=KEY, window=WINDOW, destination=target)
    assert receipt.count == 2
    assert json.loads(target.read_bytes())["status"] == "success"
    assert json.loads((tmp_path / "chunk.json.receipt.json").read_text())["raw_sha256"] == receipt.raw_sha256
    with pytest.raises(FileExistsError):
        persist_historical_chunk(payload(), instrument_key=KEY, window=WINDOW, destination=target)


@pytest.mark.parametrize("change", [
    lambda x: x.update(status="error"),
    lambda x: x["data"].update(candles=[]),
    lambda x: x["data"]["candles"][0].__setitem__(2, 90),
    lambda x: x["data"]["candles"][0].__setitem__(0, "2026-10-19T09:16:00+05:30"),
    lambda x: x["data"]["candles"].append(x["data"]["candles"][0].copy()),
    lambda x: x["data"]["candles"].reverse(),
])
def test_malformed_or_conflicting_chunks_fail_closed(change):
    item = payload()
    change(item)
    with pytest.raises(HistoricalChunkError):
        validate_historical_chunk(item, instrument_key=KEY, window=WINDOW)


def test_no_fake_provider_success_from_empty_response():
    with pytest.raises(HistoricalChunkError, match="empty"):
        validate_historical_chunk({"status": "success", "data": {"candles": []}},
                                  instrument_key=KEY, window=WINDOW)
