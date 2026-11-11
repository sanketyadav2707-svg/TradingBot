"""Calendar-gated conversion from canonical raw bars to ORB15 research bars."""

from __future__ import annotations

from typing import Iterable

from tradingbot.data.raw_futures import RawFuturesBar, validate_raw_futures_bars
from tradingbot.data.sessions import CalendarCoverageError, ExchangeSessionCalendar
from tradingbot.models import Instrument
from tradingbot.research.orb15 import ORB15Config, ORB15Result, ORBBar, run_orb15


def raw_futures_to_orb15_bars(
    bars: Iterable[RawFuturesBar],
    *,
    instrument: Instrument,
    calendar: ExchangeSessionCalendar,
) -> list[ORBBar]:
    """Convert one root's canonical raw bars after calendar and identity checks.

    ORBBar.contract_id encodes both provider instrument ID and exchange contract
    symbol. This makes contract transitions visible to the ORB engine without
    losing either identity. Bars are never resampled or forward-filled.
    """
    rows = list(bars)
    validate_raw_futures_bars(
        rows,
        expected_root_symbol=instrument.symbol,
        expected_interval_seconds=60,
    )
    converted: list[ORBBar] = []
    for bar in rows:
        try:
            if not calendar.is_trading_timestamp(bar.timestamp):
                raise CalendarCoverageError(
                    f"Raw bar {bar.timestamp.isoformat()} is outside a configured trading interval"
                )
        except CalendarCoverageError:
            raise
        converted.append(
            ORBBar(
                timestamp=bar.timestamp,
                symbol=bar.root_symbol.strip().upper(),
                contract_id=(
                    f"{bar.contract_symbol.strip().upper()}|{bar.instrument_id.strip()}"
                ),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )
    return converted


def run_orb15_from_raw_futures(
    bars: Iterable[RawFuturesBar],
    *,
    instrument: Instrument,
    calendar: ExchangeSessionCalendar,
    slippage_ticks_per_side: int,
    starting_balance_usd: float = 50_000.0,
    config: ORB15Config | None = None,
) -> ORB15Result:
    """Calendar-gated raw-contract ORB15 research entry point."""
    orb_bars = raw_futures_to_orb15_bars(
        bars,
        instrument=instrument,
        calendar=calendar,
    )
    return run_orb15(
        orb_bars,
        instrument,
        slippage_ticks_per_side=slippage_ticks_per_side,
        starting_balance_usd=starting_balance_usd,
        config=config,
    )
