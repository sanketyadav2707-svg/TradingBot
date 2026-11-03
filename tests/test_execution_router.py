from datetime import datetime, timezone

import pytest

from tradingbot.execution.router import (
    AccountRiskSnapshot,
    ExecutionMode,
    ExecutionRouter,
    OrderIntent,
    OrderRejected,
)
from tradingbot.models import Instrument, Side
from tradingbot.paper.broker import PaperBroker
from tradingbot.risk.limits import RiskGuard, RiskLimits


def _setup(mode: ExecutionMode = ExecutionMode.PAPER) -> ExecutionRouter:
    instrument = Instrument("MES", 0.25, 1.25, 5.0)
    broker = PaperBroker(instrument, slippage_ticks_per_side=1)
    guard = RiskGuard(RiskLimits(max_contracts=1, max_risk_per_trade_usd=50))
    return ExecutionRouter(broker=broker, risk_guard=guard, mode=mode)


def _intent() -> OrderIntent:
    return OrderIntent(
        instrument=Instrument("MES", 0.25, 1.25, 5.0),
        side=Side.LONG,
        stop_ticks=8,
        reference_price=6000,
        timestamp=datetime(2026, 11, 4, 14, 30, tzinfo=timezone.utc),
    )


def _account() -> AccountRiskSnapshot:
    return AccountRiskSnapshot(50_000, 50_000, 0, 0)


def test_router_sends_only_after_risk_approval() -> None:
    router = _setup()
    receipt = router.submit_entry(_intent(), _account())
    assert receipt.fill_price == 6000.25


def test_router_rejects_live_mode() -> None:
    router = _setup(ExecutionMode.LIVE)
    with pytest.raises(OrderRejected, match="live_execution_not_implemented"):
        router.submit_entry(_intent(), _account())


def test_router_emergency_halt_blocks_orders() -> None:
    router = _setup()
    router.emergency_halt()
    with pytest.raises(OrderRejected, match="emergency_halt_active"):
        router.submit_entry(_intent(), _account())


def test_router_can_require_verified_firm_profile() -> None:
    instrument = Instrument("MES", 0.25, 1.25, 5.0)
    router = ExecutionRouter(
        broker=PaperBroker(instrument),
        risk_guard=RiskGuard(RiskLimits()),
        require_firm_profile=True,
    )
    with pytest.raises(OrderRejected, match="verified_firm_profile_required"):
        router.submit_entry(_intent(), _account())
