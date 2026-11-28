from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tradingbot.data.option_quote_store import OptionTickJournal, OptionTickJournalError
from tradingbot.risk.index_options import OptionQuote

T0 = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)


def quote(at=T0):
    return OptionQuote(
        timestamp=at, instrument_key="NSE_FO|12345",
        bid=Decimal("99.05"), ask=Decimal("99.30"),
        bid_quantity=130, ask_quantity=130,
        underlying_price=Decimal("25100.45"),
        underlying_timestamp=at, implied_volatility=Decimal("0.205"),
        open_interest=5000,
    )


def test_journal_survives_restart_and_preserves_precise_prices(tmp_path):
    path = tmp_path / "option_ticks.sqlite3"
    journal = OptionTickJournal(path)
    receipt = journal.record(
        quote=quote(), source_id="decoded-upstox-fixture", received_at=T0 + timedelta(seconds=1)
    )
    assert not receipt.duplicate
    assert len(receipt.snapshot_sha256) == 64
    reloaded = OptionTickJournal(path)
    assert reloaded.count("NSE_FO|12345") == 1
    assert reloaded.latest_snapshot("NSE_FO|12345")["bid"] == "99.05"
    assert reloaded.latest_snapshot("NSE_FO|12345")["implied_volatility"] == "0.205"


def test_identical_duplicate_idempotent_and_changed_same_tick_rejected(tmp_path):
    journal = OptionTickJournal(tmp_path / "option.sqlite3")
    assert not journal.record(
        quote=quote(), source_id="provider", received_at=T0 + timedelta(seconds=1)
    ).duplicate
    assert journal.record(
        quote=quote(), source_id="provider", received_at=T0 + timedelta(seconds=2)
    ).duplicate
    assert journal.count("NSE_FO|12345") == 1
    with pytest.raises(OptionTickJournalError, match="conflicting"):
        journal.record(
            quote=replace(quote(), bid=Decimal("99.10")),
            source_id="provider", received_at=T0 + timedelta(seconds=2),
        )


def test_event_timestamp_ahead_of_receipt_fails_closed(tmp_path):
    journal = OptionTickJournal(tmp_path / "option.sqlite3")
    with pytest.raises(OptionTickJournalError, match="before_exchange"):
        journal.record(
            quote=quote(), source_id="provider", received_at=T0 - timedelta(seconds=1)
        )
    assert journal.count("NSE_FO|12345") == 0


def test_different_option_instrument_key_kept_separate(tmp_path):
    journal = OptionTickJournal(tmp_path / "option.sqlite3")
    journal.record(quote=quote(), source_id="provider", received_at=T0)
    other = replace(quote(), instrument_key="NSE_FO|67890")
    journal.record(quote=other, source_id="provider", received_at=T0)
    assert journal.count("NSE_FO|12345") == 1
    assert journal.count("NSE_FO|67890") == 1
    assert journal.latest_snapshot("NSE_FO|67890")["instrument_key"] == "NSE_FO|67890"
