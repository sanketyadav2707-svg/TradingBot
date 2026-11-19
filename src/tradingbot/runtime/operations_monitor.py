"""Deterministic, offline Phase 5 paper-operation monitoring.

This module evaluates health snapshots only. It never opens a network
connection, sends a notification, restarts an engine, or submits an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from tradingbot.data.closed_bar_inbox import InboxHealth
from tradingbot.runtime.paper_feed import PaperFeedRunnerHealth
from tradingbot.runtime.supervisor import SupervisorState, timestamp_is_fresh


@dataclass(frozen=True, slots=True)
class OperationsAlert:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class OperationsSnapshot:
    timestamp: datetime
    ready: bool
    alerts: tuple[OperationsAlert, ...]
    pending: int
    processed: int
    failed: int
    unresolved_orders: int
    open_positions: int


def evaluate_paper_operations(
    *,
    at: datetime,
    inbox: InboxHealth,
    runner: PaperFeedRunnerHealth,
    supervisor_state: SupervisorState,
    last_market_bar_received_at: datetime | None,
    require_market_data: bool = True,
    max_market_data_age_seconds: int = 120,
    max_oldest_pending_age_seconds: int = 120,
    pending_warning_threshold: int = 100,
) -> OperationsSnapshot:
    """Return a stable alert set; missing or future timestamps fail closed.

    Market-data freshness must be checked during an expected active session.
    A caller can set require_market_data=False outside market hours, but that
    never overrides inbox, risk, account or supervisor faults.
    """
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("monitor_timestamp_must_be_timezone_aware")
    if not isinstance(inbox, InboxHealth) or not isinstance(runner, PaperFeedRunnerHealth):
        raise TypeError("paper_health_snapshots_required")
    if not isinstance(supervisor_state, SupervisorState):
        raise TypeError("supervisor_state_required")
    if type(require_market_data) is not bool:
        raise TypeError("require_market_data_must_be_boolean")
    if type(max_market_data_age_seconds) is not int or max_market_data_age_seconds < 1:
        raise ValueError("invalid_max_market_data_age_seconds")
    if type(max_oldest_pending_age_seconds) is not int or max_oldest_pending_age_seconds < 1:
        raise ValueError("invalid_max_oldest_pending_age_seconds")
    if type(pending_warning_threshold) is not int or pending_warning_threshold < 1:
        raise ValueError("invalid_pending_warning_threshold")

    now = at.astimezone(timezone.utc)
    alerts: list[OperationsAlert] = []

    def alert(code: str, severity: str, message: str) -> None:
        alerts.append(OperationsAlert(code, severity, message))

    if inbox.dispatching:
        alert("AMBIGUOUS_DISPATCH", "CRITICAL", "In-flight event requires paper-ledger reconciliation")
    if inbox.failed:
        alert("FAILED_DISPATCH", "CRITICAL", "Failed market-data event requires operator review")
    if not inbox.ready and not inbox.failed and not inbox.dispatching:
        alert("INBOX_NOT_READY", "CRITICAL", "Inbox backpressure or internal health failure")
    if runner.account_halted:
        alert("ACCOUNT_HALTED", "CRITICAL", "Paper account risk halt is active")
    if runner.position_manager_halted:
        alert("POSITION_MANAGER_HALTED", "CRITICAL", "Paper position manager is halted")
    if runner.unresolved_orders:
        alert("UNRESOLVED_ORDERS", "CRITICAL", "Unresolved order lifecycle requires reconciliation")
    if runner.strategy_state != "RUNNING":
        alert("STRATEGY_NOT_RUNNING", "CRITICAL", "Paper strategy runtime is not running")
    if supervisor_state != SupervisorState.RUNNING:
        alert("SUPERVISOR_NOT_RUNNING", "CRITICAL", "Engine supervisor is not running")
    if require_market_data and not timestamp_is_fresh(
        last_market_bar_received_at, now=now, max_age_seconds=max_market_data_age_seconds
    ):
        alert("MARKET_DATA_STALE", "CRITICAL", "Market-data heartbeat missing, future or stale")
    if inbox.oldest_pending_at is not None:
        stamp = inbox.oldest_pending_at
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            alert("PENDING_TIMESTAMP_INVALID", "CRITICAL", "Inbox pending timestamp is not timezone-aware")
        else:
            age = (now - stamp.astimezone(timezone.utc)).total_seconds()
            if age < 0:
                alert("PENDING_TIMESTAMP_FUTURE", "CRITICAL", "Inbox pending timestamp is in the future")
            elif age > max_oldest_pending_age_seconds:
                alert("PENDING_TOO_OLD", "CRITICAL", "Pending candle exceeds queue latency limit")
    if inbox.pending >= pending_warning_threshold:
        alert("PENDING_QUEUE_HIGH", "WARNING", "Pending candle queue is growing")
    if not runner.ready_for_dispatch and not any(a.severity == "CRITICAL" for a in alerts):
        alert("RUNNER_NOT_READY", "CRITICAL", "Paper feed runner reports unavailable")

    return OperationsSnapshot(
        timestamp=now,
        ready=not any(a.severity == "CRITICAL" for a in alerts),
        alerts=tuple(alerts),
        pending=inbox.pending,
        processed=inbox.processed,
        failed=inbox.failed,
        unresolved_orders=runner.unresolved_orders,
        open_positions=runner.open_positions,
    )
