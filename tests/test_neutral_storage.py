from datetime import datetime, timedelta, timezone
import sqlite3

from tradingbot.accounting import PaperAccountStore
from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperFill


def _fill(order_id, side, price, timestamp):
    return PaperFill(
        order_id=order_id,
        symbol="NIFTY26DEC_FUT",
        side=side,
        quantity=65,
        requested_price=price,
        fill_price=price,
        commission_usd=1.30,
        timestamp=timestamp,
    )


def test_schema_v5_persists_neutral_columns_and_legacy_aliases_inr(tmp_path):
    database = tmp_path / "neutral-ledger.sqlite3"
    store = PaperAccountStore(database, 100000, currency_code="INR")
    instrument = Instrument(
        "NIFTY26DEC_FUT", 0.05, 0.05, 1.0,
        "INR", lot_size=65, quantity_step=65, quantity_freeze=1800,
    )
    timestamp = datetime(2026, 11, 17, 9, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    store.record_fill(_fill("entry-1", Side.LONG, 100, timestamp), instrument)

    with sqlite3.connect(database) as connection:
        version = connection.execute(
            "SELECT value FROM account_meta WHERE key='schema_version'"
        ).fetchone()[0]
        fill = connection.execute(
            """SELECT currency_code, commission_usd, commission,
                      tick_value_usd, tick_value, point_value_usd, point_value
               FROM fills WHERE order_id='entry-1'"""
        ).fetchone()
        lot = connection.execute(
            """SELECT currency_code, tick_value_usd, tick_value, point_value_usd, point_value
               FROM open_lots WHERE opening_fill_id='entry-1'"""
        ).fetchone()
        account_money = connection.execute(
            """SELECT amount, currency_code FROM account_money_v4
               WHERE entity_type='account' AND field_name='starting_balance'"""
        ).fetchone()

    assert version == "5"
    assert fill == ("INR", "1.3", "1.3", "0.05", "0.05", "1", "1")
    assert lot == ("INR", "0.05", "0.05", "1", "1")
    assert account_money == ("100000", "INR")

    store.mark_to_market(
        {"NIFTY26DEC_FUT": 101},
        timestamp + timedelta(minutes=1),
    )
    store.record_fill(
        _fill("exit-1", Side.SHORT, 101, timestamp + timedelta(minutes=2)),
        instrument,
    )
    with sqlite3.connect(database) as connection:
        trade = connection.execute(
            """SELECT currency_code, gross_pnl_usd, gross_pnl,
                      entry_commission_usd, entry_commission,
                      exit_commission_usd, exit_commission,
                      net_pnl_usd, net_pnl
               FROM closed_trades"""
        ).fetchone()
        snapshot = connection.execute(
            """SELECT currency_code, balance_usd, balance, equity_usd, equity
               FROM equity_snapshots ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        neutral_commission_rows = connection.execute(
            """SELECT COUNT(*) FROM account_money_v4
               WHERE entity_type='lifecycle_outbox' AND field_name='commission'"""
        ).fetchone()[0]

    assert trade[0] == "INR"
    assert trade[1] == trade[2]
    assert trade[3] == trade[4]
    assert trade[5] == trade[6]
    assert trade[7] == trade[8]
    assert snapshot[0] == "INR"
    assert snapshot[1] == snapshot[2]
    assert snapshot[3] == snapshot[4]
    assert neutral_commission_rows == 2

    # Reopening is idempotent and does not reinterpret or reset the INR account.
    reopened = PaperAccountStore(database, 100000, currency_code="INR")
    assert reopened.get_summary()["currency_code"] == "INR"


def test_schema_v5_neutral_columns_reject_cross_currency_reopen(tmp_path):
    database = tmp_path / "usd-ledger.sqlite3"
    PaperAccountStore(database, 50000, currency_code="USD")
    try:
        PaperAccountStore(database, 50000, currency_code="INR")
    except ValueError as exc:
        assert "currency mismatch" in str(exc)
    else:
        raise AssertionError("A USD ledger must not be reinterpreted as INR")
