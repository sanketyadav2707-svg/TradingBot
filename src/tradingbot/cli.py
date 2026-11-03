"""Command-line entry point for local backtests and data validation."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import time
from pathlib import Path

from tradingbot.backtest.engine import BacktestConfig, BacktestEngine
from tradingbot.compliance.rules import FirmComplianceGate, FirmRuleProfile
from tradingbot.data.csv_loader import load_bars
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

    return parser


def main() -> None:
    args = _build_parser().parse_args()
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
    limits = RiskLimits(
        starting_balance_usd=float(raw_risk["starting_balance_usd"]),
        max_daily_loss_usd=float(raw_risk["max_daily_loss_usd"]),
        max_total_drawdown_usd=float(raw_risk["max_total_drawdown_usd"]),
        max_risk_per_trade_usd=float(raw_risk["max_risk_per_trade_usd"]),
        max_contracts=int(raw_risk["max_contracts"]),
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
    compliance_gate = None
    if args.firm_rules:
        profile_data = _load_toml(args.firm_rules)["profile"]
        parse_time = lambda value: time.fromisoformat(value) if value else None
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
        compliance_gate = FirmComplianceGate(profile)

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
