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
