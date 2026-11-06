from datetime import datetime, timezone

import pytest

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


def test_paper_broker_rejects_non_finite_commission() -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        PaperBroker(Instrument("MES", 0.25, 1.25, 5.0), commission_per_contract_per_side_usd=float("nan"))


def test_paper_broker_rejects_fractional_slippage_ticks() -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        PaperBroker(Instrument("MES", 0.25, 1.25, 5.0), slippage_ticks_per_side=0.5)  # type: ignore[arg-type]


def test_paper_broker_rejects_non_integer_quantity_and_invalid_side() -> None:
    broker = PaperBroker(Instrument("MES", 0.25, 1.25, 5.0))
    timestamp = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="integer between"):
        broker.submit_market(side=Side.LONG, quantity=1.5, reference_price=6000, timestamp=timestamp)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="side must be"):
        broker.submit_market(side=2, quantity=1, reference_price=6000, timestamp=timestamp)  # type: ignore[arg-type]


def test_paper_broker_rejects_non_finite_reference_price() -> None:
    broker = PaperBroker(Instrument("MES", 0.25, 1.25, 5.0))
    with pytest.raises(ValueError, match="Reference price must be finite"):
        broker.submit_market(
            side=Side.LONG,
            quantity=1,
            reference_price=float("nan"),
            timestamp=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
        )
