"""Command-line entry point for local backtests and data validation."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import datetime, time
from pathlib import Path

from tradingbot.backtest.engine import BacktestConfig, BacktestEngine
from tradingbot.compliance.rules import FirmComplianceGate, FirmRuleProfile
from tradingbot.data.audit import audit_bars
from tradingbot.data.csv_loader import load_bars
from tradingbot.data.sessions import ExchangeSessionCalendar
from tradingbot.data.provider_adapters import load_databento_continuous_ohlcv_csv
from tradingbot.data.rolls import audit_contract_rolls, load_contract_roll_events_json
from tradingbot.data.orb15_adapter import run_orb15_from_raw_futures
from tradingbot.data.raw_futures import (
    build_dataset_manifest,
    load_raw_futures_csv,
    validate_raw_futures_bars,
    write_dataset_manifest,
    write_raw_futures_csv,
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
    raw_validate.add_argument("--calendar", type=Path, help="Optional verified exchange calendar JSON")

    convert_databento = sub.add_parser(
        "convert-databento-csv",
        help="Convert an existing Databento continuous OHLCV CSV to canonical raw-contract CSV",
    )
    convert_databento.add_argument("--input", required=True, type=Path)
    convert_databento.add_argument("--output", required=True, type=Path)
    convert_databento.add_argument("--symbol", required=True)
    convert_databento.add_argument("--interval-seconds", type=int, default=60)

    roll_audit = sub.add_parser(
        "audit-rolls",
        help="Audit raw-contract observations against source-backed roll-event JSON",
    )
    roll_audit.add_argument("--csv", required=True, type=Path)
    roll_audit.add_argument("--events", required=True, type=Path)
    roll_audit.add_argument("--symbol", required=True)
    roll_audit.add_argument("--interval-seconds", type=int, default=60)

    orb15 = sub.add_parser(
        "backtest-orb15-raw",
        help="Run offline ORB15 research on canonical raw-contract bars and a session calendar",
    )
    orb15.add_argument("--csv", required=True, type=Path)
    orb15.add_argument("--symbol", required=True, choices=["MES", "MNQ"])
    orb15.add_argument("--calendar", required=True, type=Path)
    orb15.add_argument("--slippage-ticks-per-side", required=True, type=int, choices=[0, 1, 2])
    orb15.add_argument("--starting-balance-usd", type=float, default=50_000.0)
    orb15.add_argument("--config-dir", type=Path, default=Path("config"))
    orb15.add_argument("--provider", default="user_supplied")
    orb15.add_argument("--dataset", default="unspecified")
    orb15.add_argument("--output", type=Path)

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

    if args.command == "convert-databento-csv":
        bars = load_databento_continuous_ohlcv_csv(
            args.input,
            expected_root_symbol=args.symbol,
            interval_seconds=args.interval_seconds,
        )
        output = write_raw_futures_csv(args.output, bars)
        print(json.dumps({
            "status": "converted",
            "rows": len(bars),
            "root_symbol": args.symbol.upper(),
            "output": str(output),
            "contract_count": len({bar.instrument_id for bar in bars}),
        }, indent=2))
        return

    if args.command == "audit-rolls":
        bars = load_raw_futures_csv(
            args.csv,
            interval_seconds=args.interval_seconds,
            expected_root_symbol=args.symbol,
        )
        events = load_contract_roll_events_json(args.events)
        report = audit_contract_rolls(
            bars,
            events,
            expected_root_symbol=args.symbol,
        )
        report["raw_csv"] = str(args.csv)
        report["events_file"] = str(args.events)
        print(json.dumps(report, indent=2))
        return

    if args.command == "backtest-orb15-raw":
        bars = load_raw_futures_csv(
            args.csv,
            interval_seconds=60,
            expected_root_symbol=args.symbol,
        )
        instruments_config = _load_toml(args.config_dir / "instruments.toml")
        raw_instrument = instruments_config["instruments"].get(args.symbol)
        if raw_instrument is None:
            raise SystemExit(f"No instrument configuration for {args.symbol}")
        instrument = Instrument(
            symbol=args.symbol,
            tick_size=float(raw_instrument["tick_size"]),
            tick_value_usd=float(raw_instrument["tick_value_usd"]),
            point_value_usd=float(raw_instrument["point_value_usd"]),
        )
        calendar = ExchangeSessionCalendar.from_json(args.calendar)
        result = run_orb15_from_raw_futures(
            bars,
            instrument=instrument,
            calendar=calendar,
            slippage_ticks_per_side=args.slippage_ticks_per_side,
            starting_balance_usd=args.starting_balance_usd,
        )
        manifest = build_dataset_manifest(
            bars,
            provider=args.provider,
            dataset=args.dataset,
            schema="raw-contract-ohlcv-1m",
            source_reference=args.csv.name,
        )
        payload = {
            "research_mode": "OFFLINE_ONLY",
            "calendar": calendar.calendar_name,
            "dataset_sha256": manifest["canonical_data_sha256"],
            "dataset_manifest": manifest,
            "metrics": result.metrics(),
            "trades": [
                {
                    "symbol": trade.symbol,
                    "contract_id": trade.contract_id,
                    "trading_date": trade.trading_date.isoformat(),
                    "side": trade.side.name,
                    "signal_time": trade.signal_time.isoformat(),
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat(),
                    "entry_price": trade.entry_price,
                    "stop_price": trade.stop_price,
                    "target_price": trade.target_price,
                    "exit_price": trade.exit_price,
                    "exit_reason": trade.exit_reason,
                    "gross_pnl_usd": trade.gross_pnl_usd,
                    "commission_usd": trade.commission_usd,
                    "slippage_usd": trade.slippage_usd,
                    "net_pnl_usd": trade.net_pnl_usd,
                }
                for trade in result.trades
            ],
            "limitations": [
                "One-minute OHLC research only; no bid/ask, queue, tick path or broker fill model.",
                "Closed-trade drawdown is not intraday mark-to-market or prop-firm trailing drawdown.",
                "Holiday windows marked review_required by the calendar must have verified product-specific overrides.",
                "A successful report is not evidence of future profitability.",
            ],
        }
        encoded = json.dumps(payload, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
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
        if args.calendar:
            calendar = ExchangeSessionCalendar.from_json(args.calendar)
            report["calendar"] = {
                "name": calendar.calendar_name,
                "timezone": calendar.timezone_name,
                "coverage_start": calendar.coverage_start.isoformat(),
                "coverage_end": calendar.coverage_end.isoformat(),
                "source_url": calendar.source_url,
            }
            report["calendar_gap_classifications"] = []
            for gap in report["gaps"]:
                previous = datetime.fromisoformat(gap["from_utc"].replace("Z", "+00:00"))
                current = datetime.fromisoformat(gap["to_utc"].replace("Z", "+00:00"))
                classification = calendar.classify_gap(
                    previous,
                    current,
                    interval_seconds=args.interval_seconds,
                )
                report["calendar_gap_classifications"].append({
                    **gap,
                    **classification,
                })
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
