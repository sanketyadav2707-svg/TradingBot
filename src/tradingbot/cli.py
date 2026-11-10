"""Command-line entry point for local backtests and data validation."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import time
from pathlib import Path

from tradingbot.backtest.engine import BacktestConfig, BacktestEngine
from tradingbot.compliance.rules import FirmComplianceGate, FirmRuleProfile
from tradingbot.data.audit import audit_bars
from tradingbot.data.csv_loader import load_bars
from tradingbot.data.raw_futures import (
    build_dataset_manifest,
    load_raw_futures_csv,
    validate_raw_futures_bars,
    write_dataset_manifest,
)
from tradingbot.models import Instrument
from tradingbot.risk.limits import RiskGuard, RiskLimits
from tradingbot.strategy.ema_cross import EmaCrossStrategy


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradingbot",
        description="Offline-first futures research and paper-trading tools.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backtest = sub.add_parser("backtest", help="Run a conservative CSV OHLCV backtest")
    backtest.add_argument("--csv", required=True, type=Path)
    backtest.add_argument("--symbol", required=True)
    backtest.add_argument("--fast", type=int, default=9)
    backtest.add_argument("--slow", type=int, default=21)
    backtest.add_argument("--stop-ticks", type=int, default=8)
    backtest.add_argument("--target-ticks", type=int, default=12)
    backtest.add_argument("--max-holding-bars", type=int, default=3)
    backtest.add_argument("--config-dir", type=Path, default=Path("config"))
    backtest.add_argument(
        "--firm-rules",
        type=Path,
        help="Optional exact account-model TOML profile; incomplete profiles fail closed",
    )

    validate = sub.add_parser("validate-data", help="Validate a CSV file without trading")
    validate.add_argument("--csv", required=True, type=Path)
    validate.add_argument("--symbol")

    audit = sub.add_parser("audit-data", help="Report OHLCV dataset coverage and time gaps")
    audit.add_argument("--csv", required=True, type=Path)
    audit.add_argument("--symbol")
    audit.add_argument("--expected-interval-seconds", type=int)
    audit.add_argument("--max-gap-examples", type=int, default=10)

    raw_validate = sub.add_parser(
        "validate-raw-data",
        help="Validate raw-contract futures CSV and optionally write a reproducible manifest",
    )
    raw_validate.add_argument("--csv", required=True, type=Path)
    raw_validate.add_argument("--symbol", required=True)
    raw_validate.add_argument("--interval-seconds", type=int, default=60)
    raw_validate.add_argument("--manifest", type=Path)
    raw_validate.add_argument("--provider", default="user_supplied")
    raw_validate.add_argument("--dataset", default="unspecified")
    raw_validate.add_argument("--schema", default="ohlcv-1m")

    databento = sub.add_parser(
        "fetch-databento",
        help="Fetch optional historical 1-minute futures data (requires data credits/API key)",
    )
    databento.add_argument("--symbol", required=True, choices=["MES", "MNQ", "M2K", "MYM", "MGC", "MCL"])
    databento.add_argument("--start", required=True, help="ISO-8601 timestamp with timezone")
    databento.add_argument("--end", required=True, help="ISO-8601 timestamp with timezone")
    databento.add_argument("--output", required=True, type=Path)
    databento.add_argument("--dataset", default="GLBX.MDP3")

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "fetch-databento":
        from tradingbot.data.databento_history import fetch_databento_ohlcv

        result = fetch_databento_ohlcv(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            output=args.output,
            dataset=args.dataset,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "validate-raw-data":
        bars = load_raw_futures_csv(
            args.csv,
            interval_seconds=args.interval_seconds,
            expected_root_symbol=args.symbol,
        )
        report = validate_raw_futures_bars(
            bars,
            expected_root_symbol=args.symbol,
            expected_interval_seconds=args.interval_seconds,
        )
        report["file"] = str(args.csv)
        if args.manifest:
            manifest = build_dataset_manifest(
                bars,
                provider=args.provider,
                dataset=args.dataset,
                schema=args.schema,
                source_reference=args.csv.name,
            )
            write_dataset_manifest(args.manifest, manifest)
            report["manifest"] = str(args.manifest)
            report["canonical_data_sha256"] = manifest["canonical_data_sha256"]
        print(json.dumps(report, indent=2))
        return

    if args.command == "validate-data":
        bars = load_bars(args.csv, args.symbol)
        print(
            json.dumps(
                {
                    "status": "valid",
                    "rows": len(bars),
                    "symbol": bars[0].symbol,
                    "first_timestamp": bars[0].timestamp.isoformat(),
                    "last_timestamp": bars[-1].timestamp.isoformat(),
                },
                indent=2,
            )
        )
        return

    if args.command == "audit-data":
        bars = load_bars(args.csv, expected_symbol=args.symbol)
        report = audit_bars(
            bars,
            expected_interval_seconds=args.expected_interval_seconds,
            max_gap_examples=args.max_gap_examples,
        )
        report["file"] = str(args.csv)
        print(json.dumps(report, indent=2))
        return

    config_dir: Path = args.config_dir
    instruments_config = _load_toml(config_dir / "instruments.toml")
    risk_config = _load_toml(config_dir / "risk.toml")
    raw_instrument = instruments_config["instruments"].get(args.symbol.upper())
    if raw_instrument is None:
        available = ", ".join(sorted(instruments_config["instruments"]))
        raise SystemExit(f"Unknown symbol {args.symbol!r}. Available: {available}")

    instrument = Instrument(
        symbol=args.symbol.upper(),
        tick_size=float(raw_instrument["tick_size"]),
        tick_value_usd=float(raw_instrument["tick_value_usd"]),
        point_value_usd=float(raw_instrument["point_value_usd"]),
    )
    raw_risk = risk_config["risk"]

    profile = None
    if args.firm_rules:
        profile_data = _load_toml(args.firm_rules)["profile"]

        def parse_time(value: str) -> time | None:
            return time.fromisoformat(value) if value else None

        profile = FirmRuleProfile(
            firm_name=str(profile_data["firm_name"]),
            account_model=str(profile_data["account_model"]),
            verified=bool(profile_data["verified"]),
            verified_on=str(profile_data["verified_on"]),
            source_url=str(profile_data["source_url"]),
            bots_permitted=bool(profile_data["bots_permitted"]),
            platform=str(profile_data["platform"]),
            timezone=str(profile_data["timezone"]),
            allowed_symbols=tuple(profile_data["allowed_symbols"]),
            latest_entry_time=parse_time(profile_data["latest_entry_time"]),
            flatten_time=parse_time(profile_data["flatten_time"]),
            max_contracts=int(profile_data["max_contracts"]) or None,
            max_daily_loss_usd=float(profile_data["max_daily_loss_usd"]) or None,
            max_total_drawdown_usd=float(profile_data["max_total_drawdown_usd"]) or None,
            no_overnight=bool(profile_data["no_overnight"]),
        )

    # Keep the local research limits at least as strict as a populated firm profile.
    # Exact trailing/EOD drawdown semantics still require account-model-specific code.
    firm_daily = profile.max_daily_loss_usd if profile else None
    firm_total = profile.max_total_drawdown_usd if profile else None
    firm_contracts = profile.max_contracts if profile else None
    limits = RiskLimits(
        starting_balance_usd=float(raw_risk["starting_balance_usd"]),
        max_daily_loss_usd=min(
            float(raw_risk["max_daily_loss_usd"]),
            firm_daily if firm_daily is not None else float(raw_risk["max_daily_loss_usd"]),
        ),
        max_total_drawdown_usd=min(
            float(raw_risk["max_total_drawdown_usd"]),
            firm_total if firm_total is not None else float(raw_risk["max_total_drawdown_usd"]),
        ),
        max_risk_per_trade_usd=float(raw_risk["max_risk_per_trade_usd"]),
        max_contracts=min(
            int(raw_risk["max_contracts"]),
            firm_contracts if firm_contracts is not None else int(raw_risk["max_contracts"]),
        ),
        max_trades_per_day=int(raw_risk["max_trades_per_day"]),
    )
    guard = RiskGuard(
        limits,
        commission_per_contract_per_side_usd=float(
            raw_risk["commission_per_contract_per_side_usd"]
        ),
        slippage_ticks_per_side=int(raw_risk["slippage_ticks_per_side"]),
    )
    bars = load_bars(args.csv, expected_symbol=instrument.symbol)
    strategy = EmaCrossStrategy(args.fast, args.slow)
    compliance_gate = FirmComplianceGate(profile) if profile else None

    engine = BacktestEngine(
        instrument=instrument,
        risk_guard=guard,
        strategy=strategy,
        config=BacktestConfig(
            stop_ticks=args.stop_ticks,
            target_ticks=args.target_ticks,
            max_holding_bars=args.max_holding_bars,
        ),
        compliance_gate=compliance_gate,
    )
    result = engine.run(bars)
    print(json.dumps(result.metrics(), indent=2))


if __name__ == "__main__":
    main()
