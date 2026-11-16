"""Dashboard runtime composition.

The default API creates a durable paper-account ledger and reads configuration.
It does not instantiate a broker, start a strategy, connect to market data, or
submit an order. A strategy/orchestrator must explicitly request a broker from
PaperAccountEngine when paper execution is intentionally started.
"""

from __future__ import annotations

import os
import sqlite3
import tomllib
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingbot.accounting import PaperAccountEngine, PaperAccountStore
from tradingbot.models import Instrument
from tradingbot.markets.nse_calendar import (
    NSEInstrumentMasterRecord,
    NSEMarketCalendar,
    load_normalized_instrument_master,
)
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
    nse_calendar: NSEMarketCalendar | None = None
    nse_master_records: tuple[NSEInstrumentMasterRecord, ...] = ()
    nse_master_configured: bool = False
    nse_master_error: str | None = None
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
                starting_balance_usd=(
                    raw_risk["starting_balance"] if "starting_balance" in raw_risk
                    else raw_risk["starting_balance_usd"]
                ),
                max_daily_loss_usd=(
                    raw_risk["daily_loss_limit"] if "daily_loss_limit" in raw_risk
                    else raw_risk["max_daily_loss_usd"]
                ),
                max_total_drawdown_usd=(
                    raw_risk["total_drawdown_limit"] if "total_drawdown_limit" in raw_risk
                    else raw_risk["max_total_drawdown_usd"]
                ),
                max_risk_per_trade_usd=(
                    raw_risk["risk_per_trade_limit"] if "risk_per_trade_limit" in raw_risk
                    else raw_risk["max_risk_per_trade_usd"]
                ),
                max_contracts=int(raw_risk["max_contracts"]),
                max_trades_per_day=int(raw_risk["max_trades_per_day"]),
                currency_code=str(raw_risk.get("currency_code", "USD")),
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
                    tick_value_usd=float(
                        raw["tick_value"] if "tick_value" in raw else raw["tick_value_usd"]
                    ),
                    point_value_usd=float(
                        raw["point_value"] if "point_value" in raw else raw["point_value_usd"]
                    ),
                    currency_code=str(raw.get("currency_code", "USD")),
                )
                runtime.instruments[normalized] = InstrumentConfig(
                    instrument=instrument,
                    name=str(raw["name"]),
                    exchange=str(raw["exchange"]),
                )
        except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
            errors.append("instrument_configuration_unavailable_or_invalid")

        if runtime.risk_limits is not None and runtime.instruments:
            mismatched = [
                symbol for symbol, record in runtime.instruments.items()
                if record.instrument.currency_code != runtime.risk_limits.currency_code
            ]
            if mismatched:
                errors.append("instrument_currency_does_not_match_account_currency")
                runtime.instruments.clear()

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
                    currency_code=runtime.risk_limits.currency_code,
                )
                runtime.paper_engine = PaperAccountEngine(
                    runtime.account_store,
                    runtime.risk_limits,
                    commission_per_contract_per_side_usd=Decimal(str(
                        raw_risk["commission_per_contract_per_side"]
                        if "commission_per_contract_per_side" in raw_risk
                        else raw_risk.get("commission_per_contract_per_side_usd", "0")
                    )),
                    slippage_ticks_per_side=int(raw_risk.get("slippage_ticks_per_side", 1)),
                )
            except (OSError, sqlite3.Error, TypeError, ValueError, RuntimeError):
                errors.append("paper_account_store_unavailable_or_invalid")

        # NSE calendar and master are read-only diagnostics. They do not
        # enable strategy execution, broker connectivity, or order routing.
        if (selected_dir / "markets" / "india_nse.toml").is_file():
            runtime.nse_calendar = NSEMarketCalendar()

        master_path = os.environ.get("TRADINGBOT_NSE_INSTRUMENT_MASTER")
        if master_path:
            runtime.nse_master_configured = True
            try:
                retrieved_at = datetime.now(timezone.utc)
                records = load_normalized_instrument_master(
                    Path(master_path).expanduser(),
                    retrieved_at,
                )
                as_of = retrieved_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
                for record in records:
                    record.validate_freshness(as_of, max_age_days=1)
                runtime.nse_master_records = records
            except (OSError, TypeError, ValueError) as exc:
                runtime.nse_master_error = str(exc)

        runtime.configuration_errors = tuple(errors)
        return runtime
