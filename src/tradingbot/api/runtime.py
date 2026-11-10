"""Dashboard runtime composition.

The default API creates a durable paper-account ledger and reads configuration.
It does not instantiate a broker, start a strategy, connect to market data, or
submit an order. A strategy/orchestrator must explicitly request a broker from
PaperAccountEngine when paper execution is intentionally started.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from tradingbot.accounting import PaperAccountEngine, PaperAccountStore
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
    account_store: PaperAccountStore | None = None
    paper_engine: PaperAccountEngine | None = None
    paper_broker: PaperBroker | None = None
    configuration_errors: tuple[str, ...] = ()

    @classmethod
    def from_config(
        cls,
        config_dir: Path | None = None,
        database_path: Path | None = None,
    ) -> "DashboardRuntime":
        module_path = Path(__file__).resolve()
        candidates = [Path.cwd().resolve(), *module_path.parents]
        project_root = next(
            (candidate for candidate in candidates if (candidate / "config" / "risk.toml").is_file()),
            Path.cwd().resolve(),
        )
        selected_dir = (config_dir or project_root / "config").expanduser().resolve()
        runtime = cls(config_dir=selected_dir)
        errors: list[str] = []
        raw_risk: dict = {}

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

        if runtime.risk_limits is not None:
            try:
                selected_db = database_path
                if selected_db is None:
                    selected_db = Path(
                        os.environ.get(
                            "TRADINGBOT_ACCOUNT_DB",
                            str(project_root / "data" / "paper_account.sqlite3"),
                        )
                    )
                runtime.account_store = PaperAccountStore(
                    selected_db,
                    starting_balance_usd=runtime.risk_limits.starting_balance_usd,
                )
                runtime.paper_engine = PaperAccountEngine(
                    runtime.account_store,
                    commission_per_contract_per_side_usd=float(
                        raw_risk.get("commission_per_contract_per_side_usd", 0.0)
                    ),
                    slippage_ticks_per_side=int(raw_risk.get("slippage_ticks_per_side", 1)),
                )
            except (OSError, TypeError, ValueError, RuntimeError):
                errors.append("paper_account_store_unavailable_or_invalid")

        runtime.configuration_errors = tuple(errors)
        return runtime
