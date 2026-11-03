from datetime import datetime, timezone

import pytest

from tradingbot.models import Bar, DataValidationError, Instrument


def test_negative_futures_price_is_valid_but_non_finite_is_not() -> None:
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bar = Bar(stamp, "MCL", -1.0, -0.5, -1.5, -1.2, 100)
    assert bar.close == -1.2

    with pytest.raises(DataValidationError, match="finite"):
        Bar(stamp, "MCL", 1.0, float("inf"), 0.5, 0.8, 100)


def test_instrument_tick_math_is_consistent() -> None:
    with pytest.raises(ValueError, match="tick_value_usd"):
        Instrument("MES", 0.25, 0.5, 5.0)
