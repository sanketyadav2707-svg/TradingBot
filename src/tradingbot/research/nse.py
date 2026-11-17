"""INR-native NSE research engine for 3–15 minute futures hypotheses.

This is an offline historical research module. It does not connect to a broker,
submit orders, or infer fees. It requires a validated NSE instrument master and
an explicit dated cost schedule. One-minute OHLC execution is conservative but
cannot reproduce queue position, spread dynamics, or intrabar path.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from tradingbot.markets.nse_calendar import (
    NSEInstrumentMasterRecord,
    NSEMarketCalendar,
    NSESessionBarGuard,
)
from tradingbot.money import FeeSchedule, Money

NSE_TZ = ZoneInfo("Asia/Kolkata")
D = Decimal


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{label}_must_be_decimal_int_or_string")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label}_must_be_a_valid_decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{label}_must_be_finite")
    return result


def _aware_timestamp(raw: str) -> datetime:
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid_iso8601_timestamp:{raw}") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("nse_bar_timestamp_must_include_timezone")
    return stamp


@dataclass(frozen=True, slots=True)
class NSEResearchInstrument:
    """Linear NSE future economics, denominated in INR per raw quantity unit."""

    master: NSEInstrumentMasterRecord
    tick_size: Decimal
    point_value_per_unit: Decimal = D("1")

    def __post_init__(self) -> None:
        if not isinstance(self.master, NSEInstrumentMasterRecord):
            raise TypeError("instrument_requires_validated_nse_master_record")
        if self.master.segment != "NSE_FO" or self.master.instrument_type not in {"FUTIDX", "FUTSTK"}:
            raise ValueError("research_engine_supports_only_nse_linear_equity_futures")
        if not self.master.nse_tradable:
            raise ValueError("bse_only_contract_not_nse_tradable")
        tick = _decimal(self.tick_size, "tick_size")
        point = _decimal(self.point_value_per_unit, "point_value_per_unit")
        if tick <= 0 or point <= 0:
            raise ValueError("instrument_tick_and_point_values_must_be_positive")
        if tick != D(self.master.tick_size):
            raise ValueError("instrument_tick_size_must_match_master")
        if self.master.currency_code != "INR":
            raise ValueError("nse_research_requires_inr_instrument")
        object.__setattr__(self, "tick_size", tick)
        object.__setattr__(self, "point_value_per_unit", point)

    @property
    def symbol(self) -> str:
        return self.master.trading_symbol

    @property
    def tick_value_per_unit(self) -> Money:
        return Money.of(self.tick_size * self.point_value_per_unit, "INR")

    def quantity_for_lots(self, lots: int) -> int:
        if type(lots) is not int or lots < 1:
            raise ValueError("lots_must_be_positive_integer")
        quantity = lots * self.master.lot_size
        if quantity % self.master.lot_size or quantity % self.master.lot_size != 0:
            raise ValueError("quantity_must_be_multiple_of_lot_size")
        if quantity > self.master.quantity_freeze:
            raise ValueError("quantity_exceeds_exchange_freeze_limit")
        if quantity % self.master.lot_size:
            raise ValueError("quantity_step_violation")
        return quantity


@dataclass(frozen=True, slots=True)
class NSEBar:
    """One raw-contract OHLCV bar; timestamp is the interval START."""

    timestamp: datetime
    symbol: str
    contract_id: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    interval_seconds: int = 60

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("nse_bar_timestamp_must_be_timezone_aware")
        if not self.symbol.strip() or not self.contract_id.strip():
            raise ValueError("nse_bar_symbol_and_contract_id_required")
        for name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, name, _decimal(getattr(self, name), name))
        prices = (self.open, self.high, self.low, self.close)
        if min(prices) <= 0:
            raise ValueError("nse_ohlc_prices_must_be_positive")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("nse_bar_high_inconsistent")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("nse_bar_low_inconsistent")
        if self.volume < 0:
            raise ValueError("nse_bar_volume_must_be_non_negative")
        if type(self.interval_seconds) is not int or self.interval_seconds != 60:
            raise ValueError("nse_phase3_requires_one_minute_bars")


@dataclass(frozen=True, slots=True)
class NSEFeeBinding:
    """Fee schedule plus its verified applicability window and provenance."""

    schedule: FeeSchedule
    valid_through: date
    verified: bool
    source_url: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.schedule, FeeSchedule):
            raise TypeError("fee_binding_requires_explicit_fee_schedule")
        if self.schedule.currency != "INR":
            raise ValueError("nse_fee_schedule_must_be_inr")
        if not isinstance(self.valid_through, date):
            raise TypeError("fee_schedule_valid_through_must_be_date")
        if self.verified and (not self.source_url or not self.source_url.startswith("https://")):
            raise ValueError("verified_fee_schedule_requires_source_url")

    def validate_period(self, first_day: date, last_day: date) -> None:
        effective = date.fromisoformat(self.schedule.effective_from)
        if first_day < effective or last_day > self.valid_through:
            raise ValueError("fee_schedule_does_not_cover_entire_research_period")


@dataclass(frozen=True, slots=True)
class NSECostScenario:
    """Explicit per-side spread and slippage assumptions; never silently zeroed."""

    spread_ticks_per_side: Decimal
    slippage_ticks_per_side: int

    def __post_init__(self) -> None:
        spread = _decimal(self.spread_ticks_per_side, "spread_ticks_per_side")
        if spread < 0:
            raise ValueError("spread_ticks_per_side_must_be_non_negative")
        if type(self.slippage_ticks_per_side) is not int or self.slippage_ticks_per_side not in (0, 1, 2):
            raise ValueError("slippage_ticks_per_side_must_be_0_1_or_2")
        object.__setattr__(self, "spread_ticks_per_side", spread)


@dataclass(frozen=True, slots=True)
class NSEResearchConfig:
    opening_range_minutes: int = 15
    signal_window_minutes: int = 120
    max_holding_minutes: int = 15
    target_r_multiple: Decimal = D("1")
    stop_buffer_ticks: int = 1
    vwap_minimum_bars: int = 15
    compression_lookback: int = 5
    compression_baseline_windows: int = 20
    compression_ratio: Decimal = D("0.65")
    lots: int = 1
    expiring_index_derivative: bool = False

    def __post_init__(self) -> None:
        for name in ("opening_range_minutes", "signal_window_minutes", "max_holding_minutes",
                     "stop_buffer_ticks", "vwap_minimum_bars", "compression_lookback",
                     "compression_baseline_windows", "lots"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name}_must_be_positive_integer")
        if self.max_holding_minutes < 3 or self.max_holding_minutes > 15:
            raise ValueError("holding_horizon_must_be_between_3_and_15_minutes")
        if self.signal_window_minutes <= self.opening_range_minutes:
            raise ValueError("signal_window_must_follow_opening_range")
        target = _decimal(self.target_r_multiple, "target_r_multiple")
        ratio = _decimal(self.compression_ratio, "compression_ratio")
        if target <= 0 or not D("0") < ratio < D("1"):
            raise ValueError("invalid_target_or_compression_ratio")
        object.__setattr__(self, "target_r_multiple", target)
        object.__setattr__(self, "compression_ratio", ratio)


@dataclass(frozen=True, slots=True)
class NSETrade:
    strategy: str
    symbol: str
    contract_id: str
    trading_date: date
    side: int
    quantity: int
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    benchmark_entry: Decimal
    benchmark_exit: Decimal
    entry_fill: Decimal
    exit_fill: Decimal
    stop_price: Decimal
    target_price: Decimal
    exit_reason: str
    gross_pnl: Money
    brokerage_and_taxes: Money
    spread_cost: Money
    slippage_cost: Money
    net_pnl: Money
    mae: Money
    mfe: Money
    bars_held: int


@dataclass(frozen=True, slots=True)
class NSEStrategyResult:
    strategy: str
    symbol: str
    currency: str
    scenario: NSECostScenario
    trades: tuple[NSETrade, ...]
    eligible_sessions: int
    invalid_sessions: int
    no_signal_sessions: int
    rejection_reasons: tuple[tuple[str, int], ...]

    def metrics(self) -> dict[str, Any]:
        net_values = [t.net_pnl.amount for t in self.trades]
        gross = sum((t.gross_pnl.amount for t in self.trades), D("0"))
        fees = sum((t.brokerage_and_taxes.amount for t in self.trades), D("0"))
        spread = sum((t.spread_cost.amount for t in self.trades), D("0"))
        slippage = sum((t.slippage_cost.amount for t in self.trades), D("0"))
        wins = [x for x in net_values if x > 0]
        losses = [x for x in net_values if x < 0]
        daily: dict[date, Decimal] = defaultdict(lambda: D("0"))
        for trade in self.trades:
            daily[trade.trading_date] += trade.net_pnl.amount
        equity = peak = drawdown = D("0")
        for value in net_values:
            equity += value
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        gross_profit = sum(wins, D("0"))
        gross_loss = abs(sum(losses, D("0")))
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "currency": self.currency,
            "eligible_sessions": self.eligible_sessions,
            "invalid_sessions": self.invalid_sessions,
            "no_signal_sessions": self.no_signal_sessions,
            "trades": len(self.trades),
            "long_trades": sum(t.side == 1 for t in self.trades),
            "short_trades": sum(t.side == -1 for t in self.trades),
            "gross_pnl": format(gross, "f"),
            "fees_and_taxes": format(fees, "f"),
            "spread_cost": format(spread, "f"),
            "slippage_cost": format(slippage, "f"),
            "net_pnl": format(sum(net_values, D("0")), "f"),
            "expectancy_per_trade": format(sum(net_values, D("0")) / len(net_values), "f") if net_values else "0",
            "win_rate_pct": round(100 * len(wins) / len(net_values), 2) if net_values else 0.0,
            "profit_factor": format(gross_profit / gross_loss, "f") if gross_loss else None,
            "closed_trade_max_drawdown": format(drawdown, "f"),
            "worst_day_net_pnl": format(min(daily.values()), "f") if daily else "0",
            "average_holding_minutes": round(sum(t.bars_held for t in self.trades) / len(self.trades), 2) if self.trades else 0.0,
            "average_mae": format(sum((t.mae.amount for t in self.trades), D("0")) / len(self.trades), "f") if self.trades else "0",
            "average_mfe": format(sum((t.mfe.amount for t in self.trades), D("0")) / len(self.trades), "f") if self.trades else "0",
            "slippage_ticks_per_side": self.scenario.slippage_ticks_per_side,
            "spread_ticks_per_side": format(self.scenario.spread_ticks_per_side, "f"),
        }


def load_nse_bars_csv(
    path: str | Path,
    *,
    expected_symbol: str,
    provider: str,
    dataset: str,
    licence_reference: str,
    retrieved_at: datetime,
) -> tuple[list[NSEBar], dict[str, Any]]:
    """Load canonical NSE raw-contract OHLCV with explicit provenance.

    This is deliberately not a guessed NSE MII parser. A market-data vendor or
    user must first normalize licensed data into this documented schema.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not all(isinstance(x, str) and x.strip() for x in (expected_symbol, provider, dataset, licence_reference)):
        raise ValueError("expected_symbol_provider_dataset_and_licence_reference_required")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at_must_be_timezone_aware")
    raw = source.read_bytes()
    file_hash = hashlib.sha256(raw).hexdigest()
    bars: list[NSEBar] = []
    previous: datetime | None = None
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "symbol", "contract_id", "open", "high", "low", "close", "volume"}
        header = set(reader.fieldnames or ())
        if header != required:
            raise ValueError("nse_ohlcv_header_must_match_canonical_schema_exactly")
        for line, row in enumerate(reader, start=2):
            try:
                bar = NSEBar(
                    timestamp=_aware_timestamp(row["timestamp"]),
                    symbol=row["symbol"].strip().upper(),
                    contract_id=row["contract_id"].strip(),
                    open=_decimal(row["open"], "open"),
                    high=_decimal(row["high"], "high"),
                    low=_decimal(row["low"], "low"),
                    close=_decimal(row["close"], "close"),
                    volume=_decimal(row["volume"], "volume"),
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(f"invalid_nse_ohlcv_row:{line}:{exc}") from exc
            if bar.symbol != expected_symbol.upper():
                raise ValueError(f"nse_symbol_mismatch_at_row:{line}")
            if previous is not None and bar.timestamp <= previous:
                raise ValueError("nse_bars_must_be_strictly_chronological_and_unique")
            previous = bar.timestamp
            bars.append(bar)
    if not bars:
        raise ValueError("nse_ohlcv_dataset_empty")
    canonical = "\n".join(
        "|".join((b.timestamp.isoformat(), b.symbol, b.contract_id,
                  format(b.open, "f"), format(b.high, "f"), format(b.low, "f"),
                  format(b.close, "f"), format(b.volume, "f")))
        for b in bars
    )
    manifest = {
        "manifest_schema_version": 1,
        "provider": provider,
        "dataset": dataset,
        "licence_reference": licence_reference,
        "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(),
        "source_file": source.name,
        "source_file_sha256": file_hash,
        "canonical_rows_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "bar_count": len(bars),
        "symbol": expected_symbol.upper(),
        "interval_seconds": 60,
        "timestamp_semantics": "interval_start",
        "timezone_policy": "timezone-aware input; exchange-local interpretation Asia/Kolkata",
        "first_timestamp": bars[0].timestamp.isoformat(),
        "last_timestamp": bars[-1].timestamp.isoformat(),
        "contract_ids": sorted({b.contract_id for b in bars}),
    }
    return bars, manifest


def _session_rows(
    bars: list[NSEBar],
    instrument: NSEResearchInstrument,
    calendar: NSEMarketCalendar,
    config: NSEResearchConfig,
) -> tuple[dict[date, list[NSEBar]], dict[str, int]]:
    if not bars:
        raise ValueError("nse_research_requires_bars")
    if any(b.symbol != instrument.symbol for b in bars):
        raise ValueError("all_bars_must_match_validated_master_symbol")
    if any(bars[i].timestamp <= bars[i - 1].timestamp for i in range(1, len(bars))):
        raise ValueError("nse_bars_must_be_strictly_chronological")
    guard = NSESessionBarGuard(
        calendar=calendar,
        segment="equity_derivatives",
        timestamp_of=lambda bar: bar.timestamp,
        expiring_index_derivative=config.expiring_index_derivative,
        interval_seconds=60,
    )
    grouped: dict[date, list[NSEBar]] = defaultdict(list)
    reasons: dict[str, int] = defaultdict(int)
    for bar in bars:
        if not guard(bar):
            reasons["outside_or_unknown_nse_session"] += 1
            continue
        if any((price / instrument.tick_size) != (price / instrument.tick_size).to_integral_value()
               for price in (bar.open, bar.high, bar.low, bar.close)):
            reasons["price_not_aligned_to_contract_tick"] += 1
            continue
        grouped[bar.timestamp.astimezone(NSE_TZ).date()].append(bar)
    return grouped, dict(reasons)


def _valid_full_session(
    day_bars: list[NSEBar],
    day: date,
    calendar: NSEMarketCalendar,
    config: NSEResearchConfig,
) -> tuple[bool, str | None]:
    try:
        window = calendar.regular_session(
            day,
            "equity_derivatives",
            expiring_index_derivative=config.expiring_index_derivative,
        )
    except Exception as exc:
        return False, f"calendar:{type(exc).__name__}"
    expected: list[datetime] = []
    cursor = window.opens_at
    while cursor + timedelta(minutes=1) <= window.closes_at:
        expected.append(cursor)
        cursor += timedelta(minutes=1)
    actual = [b.timestamp.astimezone(NSE_TZ) for b in day_bars]
    if actual != expected:
        return False, "session_missing_extra_or_misaligned_bars"
    contracts = {b.contract_id for b in day_bars}
    if len(contracts) != 1:
        return False, "contract_identity_changed_inside_session"
    return True, None


def _signal(
    strategy: str,
    rows: list[NSEBar],
    index: int,
    vwap_values: list[Decimal],
    cfg: NSEResearchConfig,
    tick: Decimal,
) -> tuple[int, Decimal] | None:
    bar = rows[index]
    if strategy == "orb15":
        return None
    if strategy == "vwap_pullback":
        if index < cfg.vwap_minimum_bars:
            return None
        prev = rows[index - 1]
        if prev.close <= vwap_values[index - 1] and bar.low <= vwap_values[index] and bar.close > vwap_values[index] and bar.close > prev.high:
            stop = min(x.low for x in rows[max(0, index - 4):index + 1]) - tick * cfg.stop_buffer_ticks
            return 1, stop
        if prev.close >= vwap_values[index - 1] and bar.high >= vwap_values[index] and bar.close < vwap_values[index] and bar.close < prev.low:
            stop = max(x.high for x in rows[max(0, index - 4):index + 1]) + tick * cfg.stop_buffer_ticks
            return -1, stop
        return None
    if strategy == "compression_breakout":
        lookback, baseline = cfg.compression_lookback, cfg.compression_baseline_windows
        if index < lookback + baseline + 1:
            return None
        prior = rows[index - lookback:index]
        ranges = []
        for end in range(index - lookback - baseline + 1, index - lookback + 1):
            sample = rows[end - lookback:end]
            ranges.append(max(x.high for x in sample) - min(x.low for x in sample))
        reference = D(str(median(ranges)))
        width = max(x.high for x in prior) - min(x.low for x in prior)
        if reference <= 0 or width > cfg.compression_ratio * reference:
            return None
        upper, lower = max(x.high for x in prior), min(x.low for x in prior)
        if bar.close >= upper + tick:
            return 1, lower - tick * cfg.stop_buffer_ticks
        if bar.close <= lower - tick:
            return -1, upper + tick * cfg.stop_buffer_ticks
        return None
    raise ValueError(f"unsupported_nse_strategy:{strategy}")


def _trade_for_signal(
    strategy: str,
    rows: list[NSEBar],
    signal_index: int,
    side: int,
    stop: Decimal,
    instrument: NSEResearchInstrument,
    fees: NSEFeeBinding,
    scenario: NSECostScenario,
    config: NSEResearchConfig,
) -> NSETrade | None:
    entry_index = signal_index + 1
    if entry_index >= len(rows):
        return None
    signal_bar, entry_bar = rows[signal_index], rows[entry_index]
    if entry_bar.timestamp != signal_bar.timestamp + timedelta(minutes=1):
        return None
    if entry_bar.contract_id != signal_bar.contract_id:
        return None
    quantity = instrument.quantity_for_lots(config.lots)
    tick = instrument.tick_size
    direction = D(side)
    per_side_ticks = scenario.spread_ticks_per_side + D(scenario.slippage_ticks_per_side)
    adverse = tick * per_side_ticks
    entry_fill = entry_bar.open + direction * adverse
    if (side == 1 and stop >= entry_fill) or (side == -1 and stop <= entry_fill):
        return None
    risk = abs(entry_fill - stop)
    target = entry_fill + direction * risk * config.target_r_multiple
    max_exit_index = min(entry_index + config.max_holding_minutes - 1, len(rows) - 1)
    exit_index = max_exit_index
    exit_reason = "TIME"
    exit_base = rows[max_exit_index].close
    mae_points = D("0")
    mfe_points = D("0")
    for j in range(entry_index, max_exit_index + 1):
        current = rows[j]
        if current.contract_id != entry_bar.contract_id:
            return None
        adverse_excursion = (entry_fill - current.low) if side == 1 else (current.high - entry_fill)
        favourable_excursion = (current.high - entry_fill) if side == 1 else (entry_fill - current.low)
        mae_points = max(mae_points, adverse_excursion, D("0"))
        mfe_points = max(mfe_points, favourable_excursion, D("0"))
        stop_hit = current.low <= stop if side == 1 else current.high >= stop
        target_hit = current.high >= target if side == 1 else current.low <= target
        if stop_hit:
            exit_reason = "STOP"
            # A gap through a stop is filled at the worse opening price.
            exit_base = min(current.open, stop) if side == 1 else max(current.open, stop)
            exit_index = j
            break
        if target_hit:
            exit_reason = "TARGET"
            # Do not assume price improvement when a target is gapped through.
            exit_base = target
            exit_index = j
            break
    exit_bar = rows[exit_index]
    exit_fill = exit_base - direction * adverse
    point_value = instrument.point_value_per_unit
    gross_amount = (exit_base - entry_bar.open) * direction * point_value * quantity
    fee_money = fees.schedule.round_trip(quantity)
    spread_amount = tick * scenario.spread_ticks_per_side * D("2") * point_value * quantity
    slippage_amount = tick * D(scenario.slippage_ticks_per_side) * D("2") * point_value * quantity
    gross = Money.of(gross_amount, "INR")
    spread_cost = Money.of(spread_amount, "INR")
    slippage_cost = Money.of(slippage_amount, "INR")
    net = gross - fee_money - spread_cost - slippage_cost
    return NSETrade(
        strategy=strategy,
        symbol=instrument.symbol,
        contract_id=entry_bar.contract_id,
        trading_date=entry_bar.timestamp.astimezone(NSE_TZ).date(),
        side=side,
        quantity=quantity,
        signal_time=signal_bar.timestamp + timedelta(minutes=1),
        entry_time=entry_bar.timestamp,
        exit_time=exit_bar.timestamp + timedelta(minutes=1),
        benchmark_entry=entry_bar.open,
        benchmark_exit=exit_base,
        entry_fill=entry_fill,
        exit_fill=exit_fill,
        stop_price=stop,
        target_price=target,
        exit_reason=exit_reason,
        gross_pnl=gross,
        brokerage_and_taxes=fee_money,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        net_pnl=net,
        mae=Money.of(mae_points * point_value * quantity, "INR"),
        mfe=Money.of(mfe_points * point_value * quantity, "INR"),
        bars_held=exit_index - entry_index + 1,
    )


def run_nse_strategy(
    bars: list[NSEBar],
    instrument: NSEResearchInstrument,
    *,
    strategy: str,
    calendar: NSEMarketCalendar,
    fee_binding: NSEFeeBinding,
    scenario: NSECostScenario,
    config: NSEResearchConfig | None = None,
) -> NSEStrategyResult:
    """Run one frozen NSE hypothesis; one trade maximum per complete session."""
    if strategy not in {"orb15", "vwap_pullback", "compression_breakout"}:
        raise ValueError("strategy_must_be_orb15_vwap_pullback_or_compression_breakout")
    cfg = config or NSEResearchConfig()
    if not bars:
        raise ValueError("nse_research_requires_bars")
    first_day = bars[0].timestamp.astimezone(NSE_TZ).date()
    last_day = bars[-1].timestamp.astimezone(NSE_TZ).date()
    fee_binding.validate_period(first_day, last_day)
    grouped, initial_reasons = _session_rows(bars, instrument, calendar, cfg)
    trades: list[NSETrade] = []
    eligible = invalid = no_signal = 0
    reasons: dict[str, int] = defaultdict(int, initial_reasons)
    for day in sorted(grouped):
        rows = grouped[day]
        valid, reason = _valid_full_session(rows, day, calendar, cfg)
        if not valid:
            invalid += 1
            reasons[reason or "invalid_session"] += 1
            continue
        eligible += 1
        window = calendar.regular_session(
            day, "equity_derivatives",
            expiring_index_derivative=cfg.expiring_index_derivative,
        )
        latest_entry = window.closes_at - timedelta(minutes=cfg.max_holding_minutes)
        vwap_values: list[Decimal] = []
        numerator = denominator = D("0")
        for row in rows:
            typical = (row.high + row.low + row.close) / D("3")
            numerator += typical * row.volume
            denominator += row.volume
            vwap_values.append(numerator / denominator if denominator else typical)
        signal_index = None
        signal_value = None
        start = cfg.opening_range_minutes
        end = min(cfg.signal_window_minutes, len(rows) - cfg.max_holding_minutes)
        for i in range(start, end):
            stamp = rows[i].timestamp
            if stamp >= latest_entry:
                break
            if strategy == "orb15":
                opening = rows[:cfg.opening_range_minutes]
                upper = max(x.high for x in opening)
                lower = min(x.low for x in opening)
                if rows[i].close >= upper + instrument.tick_size:
                    signal_value = (1, lower - instrument.tick_size * cfg.stop_buffer_ticks)
                elif rows[i].close <= lower - instrument.tick_size:
                    signal_value = (-1, upper + instrument.tick_size * cfg.stop_buffer_ticks)
            else:
                signal_value = _signal(strategy, rows, i, vwap_values, cfg, instrument.tick_size)
            if signal_value is not None:
                signal_index = i
                break
        if signal_index is None or signal_value is None:
            no_signal += 1
            continue
        trade = _trade_for_signal(
            strategy, rows, signal_index, signal_value[0], signal_value[1],
            instrument, fee_binding, scenario, cfg,
        )
        if trade is None:
            reasons["signal_rejected_or_entry_unavailable"] += 1
            continue
        trades.append(trade)
    return NSEStrategyResult(
        strategy=strategy,
        symbol=instrument.symbol,
        currency="INR",
        scenario=scenario,
        trades=tuple(trades),
        eligible_sessions=eligible,
        invalid_sessions=invalid,
        no_signal_sessions=no_signal,
        rejection_reasons=tuple(sorted(reasons.items())),
    )


@dataclass(frozen=True, slots=True)
class NSEChronologicalSplit:
    development: tuple[NSEBar, ...]
    holdout: tuple[NSEBar, ...]
    development_dates: tuple[date, ...]
    holdout_dates: tuple[date, ...]
    cutoff_date: date
    latest_date: date
    holdout_calendar_days: int

    def metadata(self) -> dict[str, Any]:
        return {
            "method": "chronological_calendar_day_holdout",
            "timezone": "Asia/Kolkata",
            "holdout_calendar_days": self.holdout_calendar_days,
            "cutoff_date_inclusive": self.cutoff_date.isoformat(),
            "latest_trading_date": self.latest_date.isoformat(),
            "development_first_date": self.development_dates[0].isoformat(),
            "development_last_date": self.development_dates[-1].isoformat(),
            "development_sessions": len(self.development_dates),
            "holdout_first_date": self.holdout_dates[0].isoformat(),
            "holdout_last_date": self.holdout_dates[-1].isoformat(),
            "holdout_sessions": len(self.holdout_dates),
            "date_overlap": False,
            "randomized": False,
            "holdout_used_for_tuning": False,
        }


def split_nse_chronological_holdout(
    bars: Iterable[NSEBar],
    *,
    holdout_calendar_days: int = 90,
    minimum_development_sessions: int = 20,
    minimum_holdout_sessions: int = 20,
) -> NSEChronologicalSplit:
    rows = list(bars)
    if not rows:
        raise ValueError("cannot_split_empty_nse_dataset")
    if type(holdout_calendar_days) is not int or holdout_calendar_days < 90:
        raise ValueError("nse_holdout_must_be_at_least_90_calendar_days")
    if any(rows[i].timestamp <= rows[i - 1].timestamp for i in range(1, len(rows))):
        raise ValueError("nse_bars_must_be_strictly_chronological")
    grouped: dict[date, list[NSEBar]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp.astimezone(NSE_TZ).date()].append(row)
    dates = sorted(grouped)
    latest = dates[-1]
    cutoff = latest - timedelta(days=holdout_calendar_days - 1)
    development_dates = tuple(day for day in dates if day < cutoff)
    holdout_dates = tuple(day for day in dates if day >= cutoff)
    if len(development_dates) < minimum_development_sessions:
        raise ValueError("insufficient_nse_development_sessions")
    if len(holdout_dates) < minimum_holdout_sessions:
        raise ValueError("insufficient_nse_holdout_sessions")
    if not development_dates or not holdout_dates or development_dates[-1] >= holdout_dates[0]:
        raise ValueError("nse_chronological_split_empty_or_overlapping")
    return NSEChronologicalSplit(
        development=tuple(row for day in development_dates for row in grouped[day]),
        holdout=tuple(row for day in holdout_dates for row in grouped[day]),
        development_dates=development_dates,
        holdout_dates=holdout_dates,
        cutoff_date=cutoff,
        latest_date=latest,
        holdout_calendar_days=holdout_calendar_days,
    )


def evaluate_nse_strategy_set(
    bars: list[NSEBar],
    instrument: NSEResearchInstrument,
    *,
    calendar: NSEMarketCalendar,
    fee_binding: NSEFeeBinding,
    scenarios: tuple[NSECostScenario, ...],
    config: NSEResearchConfig | None = None,
    holdout_calendar_days: int = 90,
) -> dict[str, Any]:
    """Evaluate three frozen hypotheses on development and untouched final holdout."""
    split = split_nse_chronological_holdout(
        bars, holdout_calendar_days=holdout_calendar_days
    )
    periods = {"development": split.development, "protected_holdout": split.holdout}
    report: dict[str, Any] = {
        "schema_version": 1,
        "research_mode": "NSE_INR_FROZEN_STRATEGY_EVALUATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instrument": {
            "symbol": instrument.symbol,
            "exchange_token": instrument.master.exchange_token,
            "instrument_type": instrument.master.instrument_type,
            "expiry": instrument.master.expiry.isoformat() if instrument.master.expiry else None,
            "lot_size": instrument.master.lot_size,
            "quantity_freeze": instrument.master.quantity_freeze,
            "tick_size": format(instrument.tick_size, "f"),
            "point_value_per_unit_inr": format(instrument.point_value_per_unit, "f"),
        },
        "fees": {
            "schedule_id": fee_binding.schedule.schedule_id,
            "effective_from": fee_binding.schedule.effective_from,
            "valid_through": fee_binding.valid_through.isoformat(),
            "verified": fee_binding.verified,
            "source_url": fee_binding.source_url,
        },
        "data": {
            "bar_count": len(bars),
            "first_timestamp": bars[0].timestamp.isoformat(),
            "last_timestamp": bars[-1].timestamp.isoformat(),
            "contract_ids": sorted({b.contract_id for b in bars}),
            "unique_trading_dates": len({b.timestamp.astimezone(NSE_TZ).date() for b in bars}),
        },
        "split": split.metadata(),
        "assumptions": {
            "strategies": ["orb15", "vwap_pullback", "compression_breakout"],
            "cost_scenarios": [
                {"spread_ticks_per_side": format(s.spread_ticks_per_side, "f"),
                 "slippage_ticks_per_side": s.slippage_ticks_per_side}
                for s in scenarios
            ],
            "parameters_tuned_on_holdout": False,
            "execution": "one-minute OHLC; next-bar-open; stop-first on ambiguous bars",
            "limitations": [
                "No historical bid/ask, queue priority, partial fills, latency or market impact.",
                "Minute OHLC cannot reveal intrabar path; stop-first is conservative but not a tick replay.",
                "Broker fees are only as reliable as the supplied dated schedule.",
                "No live orders or broker connections are possible from this module.",
            ],
            "promotion_blocked_if_fee_schedule_unverified": not fee_binding.verified,
        },
        "results": {},
    }
    for period_name, period_bars in periods.items():
        results: dict[str, Any] = {}
        for strategy in ("orb15", "vwap_pullback", "compression_breakout"):
            for scenario in scenarios:
                result = run_nse_strategy(
                    list(period_bars), instrument, strategy=strategy,
                    calendar=calendar, fee_binding=fee_binding,
                    scenario=scenario, config=config,
                )
                key = f"{strategy}_spread{scenario.spread_ticks_per_side}_slip{scenario.slippage_ticks_per_side}"
                results[key] = {
                    "metrics": result.metrics(),
                    "rejection_reasons": dict(result.rejection_reasons),
                }
        report["results"][period_name] = results
    return report


def write_nse_research_report(path: str | Path, report: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(destination)
    return destination
