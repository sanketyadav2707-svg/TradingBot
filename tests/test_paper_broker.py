from datetime import datetime, timezone

from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperBroker


def test_paper_broker_applies_adverse_slippage() -> None:
    broker = PaperBroker(Instrument("MES", 0.25, 1.25, 5.0), slippage_ticks_per_side=1)
    fill = broker.submit_market(
        side=Side.LONG,
        quantity=1,
        reference_price=6000.0,
        timestamp=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
    )
    assert fill.fill_price == 6000.25
    assert len(broker.fills) == 1


def test_paper_broker_supports_negative_futures_price() -> None:
    broker = PaperBroker(Instrument("MCL", 0.01, 1.0, 100.0), slippage_ticks_per_side=1)
    fill = broker.submit_market(
        side=Side.LONG,
        quantity=1,
        reference_price=-10.0,
        timestamp=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
    )
    assert fill.fill_price == -9.99
