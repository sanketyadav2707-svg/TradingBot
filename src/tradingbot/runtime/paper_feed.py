"""Phase 5 orchestration for durable-feed to risk-gated paper execution.

No network, scheduler, credentials or live broker are created here. An external
authorized provider adapter must normalize a completed candle to Bar and call
ingest(). A service manager may call drain_one() at a controlled cadence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tradingbot.data.closed_bar_inbox import ClosedBarInbox, InboxEvent
from tradingbot.data.continuity import ClosedBarContinuityGuard
from tradingbot.models import Bar
from tradingbot.runtime.positions import PaperTradingLoop
from tradingbot.runtime.strategy import RuntimeState


@dataclass(frozen=True, slots=True)
class PaperFeedRunnerHealth:
    inbox_ready: bool
    strategy_state: str
    position_manager_halted: bool
    account_halted: bool
    open_positions: int
    unresolved_orders: int
    ready_for_dispatch: bool


class PaperFeedRunner:
    """Compose durable closed-bar ingestion and the Phase 4 paper engine."""

    def __init__(
        self,
        *,
        inbox: ClosedBarInbox,
        paper_loop: PaperTradingLoop,
        expected_symbol: str,
        source_id: str,
        continuity_guard: ClosedBarContinuityGuard | None = None,
    ) -> None:
        if not isinstance(inbox, ClosedBarInbox):
            raise TypeError("closed_bar_inbox_required")
        if not isinstance(paper_loop, PaperTradingLoop):
            raise TypeError("paper_trading_loop_required")
        if not isinstance(expected_symbol, str) or not expected_symbol.strip():
            raise ValueError("expected_symbol_required")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id_required")
        self.inbox = inbox
        self.paper_loop = paper_loop
        self.expected_symbol = expected_symbol.strip().upper()
        self.source_id = source_id.strip()
        if continuity_guard is not None and not isinstance(continuity_guard, ClosedBarContinuityGuard):
            raise TypeError("continuity_guard_must_be_closed_bar_guard")
        if continuity_guard is not None and continuity_guard.symbol != self.expected_symbol:
            raise ValueError("continuity_guard_symbol_mismatch")
        self.continuity_guard = continuity_guard

    def ingest(self, bar: Bar, *, received_at: datetime) -> int:
        if not isinstance(bar, Bar):
            raise TypeError("normalized_bar_required")
        if bar.symbol.strip().upper() != self.expected_symbol:
            raise ValueError("feed_symbol_does_not_match_runner")
        return self.inbox.enqueue(bar, source_id=self.source_id, received_at=received_at)

    def _dispatch(self, bar: Bar, received_at: datetime) -> None:
        if self.continuity_guard is not None:
            decision = self.continuity_guard.inspect(bar)
            if not decision.accepted:
                raise RuntimeError("market_data_continuity_failure:" + decision.reason)
        self.paper_loop.process_closed_bar(bar, received_at=received_at)
        if self.paper_loop.strategy_runtime.state != RuntimeState.RUNNING:
            raise RuntimeError(
                "paper_strategy_runtime_not_running:" + self.paper_loop.strategy_runtime.reason
            )
        if self.paper_loop.position_manager.halted:
            raise RuntimeError(
                "paper_position_manager_halted:" + self.paper_loop.position_manager.reason
            )
        if self.paper_loop.position_manager.engine.halted:
            raise RuntimeError("paper_account_engine_halted")

    def drain_one(self) -> InboxEvent | None:
        return self.inbox.dispatch_next(self._dispatch)

    def health(self) -> PaperFeedRunnerHealth:
        engine = self.paper_loop.position_manager.engine
        inbox_health = self.inbox.health()
        open_positions = len(engine.store.list_positions())
        unresolved_orders = len(engine.order_lifecycle.list_unresolved_orders())
        manager_halted = self.paper_loop.position_manager.halted
        account_halted = engine.halted
        strategy_state = self.paper_loop.strategy_runtime.state.value
        ready = (
            inbox_health.ready
            and (self.continuity_guard is None or not self.continuity_guard.halted)
            and strategy_state == RuntimeState.RUNNING.value
            and not manager_halted
            and not account_halted
            and unresolved_orders == 0
        )
        return PaperFeedRunnerHealth(
            inbox_ready=inbox_health.ready,
            strategy_state=strategy_state,
            position_manager_halted=manager_halted,
            account_halted=account_halted,
            open_positions=open_positions,
            unresolved_orders=unresolved_orders,
            ready_for_dispatch=ready,
        )
