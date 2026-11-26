from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import sqlite3

import pytest

from tradingbot.data.option_quote_store import OptionTickJournal
from tradingbot.research.option_replay import load_option_replay, snapshot_as_of, OptionReplayError
from tradingbot.risk.index_options import OptionQuote

T = datetime(2026, 11, 26, 5, tzinfo=timezone.utc)


def seed(tmp_path):
    path = tmp_path / "ticks.db"
    journal = OptionTickJournal(path)
    q = OptionQuote(timestamp=T, instrument_key="NSE_FO|100",
                    bid=D("99"), ask=D("100"), bid_quantity=65, ask_quantity=65,
                    underlying_price=D("25000"), underlying_timestamp=T,
                    implied_volatility=D("0.2"), open_interest=500)
    journal.record(quote=q, source_id="fixture", received_at=T+timedelta(seconds=1))
    return path, journal, q


def load(path, **kwargs):
    return load_option_replay(path, instrument_key="NSE_FO|100", source_id="fixture",
                              start=T, end=T+timedelta(minutes=1), **kwargs)


def test_no_future_receipt_and_stale_quote(tmp_path):
    path, _, q = seed(tmp_path)
    rows = load(path)
    assert len(rows) == 1
    assert snapshot_as_of(rows, decision_at=T) is None
    assert snapshot_as_of(rows, decision_at=T+timedelta(seconds=1)).quote == q
    assert snapshot_as_of(rows, decision_at=T+timedelta(seconds=3)) is None


def test_corrupt_payload_rejected(tmp_path):
    path, _, _ = seed(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE option_quote_ticks SET quote_json='{}'")
    with pytest.raises(OptionReplayError, match="hash"):
        load(path)


def test_out_of_order_exchange_ticks_rejected(tmp_path):
    path, journal, q = seed(tmp_path)
    journal.record(quote=replace(q, timestamp=T-timedelta(seconds=1)),
                   source_id="fixture", received_at=T+timedelta(seconds=2))
    with pytest.raises(OptionReplayError, match="out_of_order"):
        load(path)


def test_bounded_replay_rejects_truncation(tmp_path):
    path, journal, q = seed(tmp_path)
    journal.record(quote=replace(q, timestamp=T+timedelta(seconds=2)),
                   source_id="fixture", received_at=T+timedelta(seconds=2))
    with pytest.raises(OptionReplayError, match="limit"):
        load(path, max_rows=1)
