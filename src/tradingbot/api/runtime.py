"""Explicitly injected read-only runtime snapshots for the dashboard API.

The default service does not construct a trading session. A host may attach
snapshots from existing runtime components; absent data remains unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingbot.api.schemas import (
    EquityPointResponse,
    OperationalEventResponse,
    PositionResponse,
    TradeResponse,
)
from tradingbot.execution.router import AccountRiskSnapshot
from tradingbot.risk.limits import RiskGuard


@dataclass(slots=True)
class DashboardRuntime:
    """Read-only data supplied by a running paper session.

    None means the source does not exist or is not attached. An empty tuple
    means the source is attached and has no records. This distinction prevents
    an unavailable portfolio from being displayed as an empty portfolio.
    """

    account_snapshot: AccountRiskSnapshot | None = None
    risk_guard: RiskGuard | None = None
    strategy_name: str | None = None
    strategy_state: str = "UNKNOWN"
    market_symbols: tuple[str, ...] = ()
    market_data_connected: bool = False
    market_data_last_update: str | None = None
    positions: tuple[PositionResponse, ...] | None = None
    trades: tuple[TradeResponse, ...] | None = None
    equity_points: tuple[EquityPointResponse, ...] | None = None
    events: tuple[OperationalEventResponse, ...] | None = None
    source_name: str = "injected-paper-runtime"
