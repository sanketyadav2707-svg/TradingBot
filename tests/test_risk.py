import pytest

from tradingbot.models import Instrument
from tradingbot.risk.limits import RiskGuard, RiskLimits


def _instrument() -> Instrument:
    return Instrument("MES", 0.25, 1.25, 5.0)


def test_risk_guard_approves_within_budget() -> None:
    guard = RiskGuard(RiskLimits(max_risk_per_trade_usd=50, max_contracts=3))
    decision = guard.evaluate_entry(
        instrument=_instrument(),
        stop_ticks=8,
        equity_usd=50_000,
        peak_equity_usd=50_000,
        daily_pnl_usd=0,
        trades_today=0,
    )
    assert decision.approved
    assert decision.quantity == 3


def test_risk_guard_blocks_when_daily_loss_limit_reached() -> None:
    guard = RiskGuard(RiskLimits(max_daily_loss_usd=300))
    decision = guard.evaluate_entry(
        instrument=_instrument(),
        stop_ticks=8,
        equity_usd=49_700,
        peak_equity_usd=50_000,
        daily_pnl_usd=-300,
        trades_today=0,
    )
    assert not decision.approved
    assert decision.reason == "maximum_daily_loss_reached"


def test_risk_guard_accounts_for_remaining_drawdown_buffer() -> None:
    guard = RiskGuard(
        RiskLimits(max_total_drawdown_usd=30, max_risk_per_trade_usd=50, max_contracts=5)
    )
    decision = guard.evaluate_entry(
        instrument=_instrument(),
        stop_ticks=8,
        equity_usd=49_985,
        peak_equity_usd=50_000,
        daily_pnl_usd=0,
        trades_today=0,
    )
    assert decision.approved
    assert decision.quantity == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_risk_limits_reject_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        RiskLimits(max_daily_loss_usd=value)


@pytest.mark.parametrize("value", [1.5, True, 0])
def test_risk_limits_require_integer_contract_and_trade_counts(value: object) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        RiskLimits(max_contracts=value)  # type: ignore[arg-type]


def test_risk_guard_fails_closed_on_invalid_account_snapshot() -> None:
    guard = RiskGuard(RiskLimits())
    common = {
        "instrument": _instrument(),
        "stop_ticks": 8,
        "daily_pnl_usd": 0,
        "trades_today": 0,
    }
    invalid_snapshots = (
        {"equity_usd": float("nan"), "peak_equity_usd": 50_000},
        {"equity_usd": 50_001, "peak_equity_usd": 50_000},
        {"equity_usd": 50_000, "peak_equity_usd": 50_000, "trades_today": -1},
    )
    for snapshot in invalid_snapshots:
        args = {**common, "equity_usd": 50_000, "peak_equity_usd": 50_000}
        args.update(snapshot)
        decision = guard.evaluate_entry(**args)
        assert not decision.approved
        assert decision.reason == "invalid_account_snapshot"


def test_risk_guard_rejects_non_finite_commission_and_fractional_slippage() -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        RiskGuard(RiskLimits(), commission_per_contract_per_side_usd=float("nan"))
    with pytest.raises(ValueError, match="non-negative integer"):
        RiskGuard(RiskLimits(), slippage_ticks_per_side=0.5)  # type: ignore[arg-type]
