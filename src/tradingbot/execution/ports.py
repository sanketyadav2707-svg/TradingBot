"""Broker port contract shared by paper and future firm-specific adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from tradingbot.models import Side


class ExecutionPort(Protocol):
    """Minimal market-order interface. Live implementations are intentionally absent."""

    def submit_market(
        self,
        *,
        side: Side,
        quantity: int,
        reference_price: float,
        timestamp: datetime,
    ) -> object:
        """Submit an order and return a provider-specific receipt."""
        ...
