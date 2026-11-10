"""Read-only runtime adapter.

The shipped application deliberately does not instantiate a broker, strategy runner,
market-data feed, or account snapshot. Those objects can be injected by a future local
orchestrator, but this module never starts trading or fabricates account state.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from tradingbot.models import Instrument
from tradingbot.paper.broker import PaperBroker
from tradingbot.risk.limits import RiskLimits


@dataclass(frozen=True, slots=True)
class InstrumentConfig:
    instrument: Instrument
    name: str
    exchange: str


@dataclass(slots=True)
class DashboardRuntime:
    config_dir: Path
    risk_limits: RiskLimits | None = None
    instruments: dict[str, InstrumentConfig] = field(default_factory=dict)
    paper_broker: PaperBroker | None = None
    configuration_errors: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, config_dir: Path | None = None) -> "DashboardRuntime":
        project_root = Path(__file__).resolve().parents[3]
        selected_dir = (config_dir or project_root / "config").expanduser().resolve()
        runtime = cls(config_dir=selected_dir)
        errors: list[str] = []

        risk_path = selected_dir / "risk.toml"
        try:
            with risk_path.open("rb") as handle:
                raw_risk = tomllib.load(handle)["risk"]
            runtime.risk_limits = RiskLimits(
                starting_balance_usd=float(raw_risk["starting_balance_usd"]),
                max_daily_loss_usd=float(raw_risk["max_daily_loss_usd"]),
                max_total_drawdown_usd=float(raw_risk["max_total_drawdown_usd"]),
                max_risk_per_trade_usd=float(raw_risk["max_risk_per_trade_usd"]),
                max_contracts=int(raw_risk["max_contracts"]),
                max_trades_per_day=int(raw_risk["max_trades_per_day"]),
            )
        except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
            errors.append("risk_configuration_unavailable_or_invalid")

        instruments_path = selected_dir / "instruments.toml"
        try:
            with instruments_path.open("rb") as handle:
                raw_instruments = tomllib.load(handle)["instruments"]
            for symbol, raw in raw_instruments.items():
                normalized = str(symbol).upper()
                instrument = Instrument(
                    symbol=normalized,
                    tick_size=float(raw["tick_size"]),
                    tick_value_usd=float(raw["tick_value_usd"]),
                    point_value_usd=float(raw["point_value_usd"]),
                )
                runtime.instruments[normalized] = InstrumentConfig(
                    instrument=instrument,
                    name=str(raw["name"]),
                    exchange=str(raw["exchange"]),
                )
        except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
            errors.append("instrument_configuration_unavailable_or_invalid")

        runtime.configuration_errors = tuple(errors)
        return runtime
