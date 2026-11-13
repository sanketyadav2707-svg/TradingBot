"""Fail-closed watchdog for the short-horizon trading engine.

The supervisor is deliberately tick-driven: a service manager or scheduler calls
poll() at a fixed cadence. It creates no hidden threads, timers, network clients,
or broker connections. Restarts are bounded and never bypass recovery checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Callable, Sequence


class SupervisorState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class SupervisorEvent:
    state: SupervisorState
    timestamp: datetime
    reason: str
    restart_attempt: int


def _aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def timestamp_is_fresh(
    observed_at: datetime | None,
    *,
    now: datetime,
    max_age_seconds: int,
) -> bool:
    """Return False for missing, stale, future-dated, or invalid market timestamps."""
    if type(max_age_seconds) is not int or max_age_seconds < 1:
        raise ValueError("max_age_seconds must be a positive integer")
    try:
        current = _aware(now, "now")
        observed = _aware(observed_at, "observed_at") if observed_at is not None else None
    except (TypeError, ValueError):
        return False
    if observed is None:
        return False
    age = (current - observed).total_seconds()
    return 0 <= age <= max_age_seconds


class EngineSupervisor:
    """Bounded restart controller that requires explicit recovery approval.

    Call heartbeat() only after the engine has completed a healthy work cycle.
    A process heartbeat is not a substitute for market-data freshness: inject
    freshness and account-reconciliation checks in health_checks/recovery_checks.
    """

    def __init__(
        self,
        *,
        start_engine: Callable[[], bool],
        stop_engine: Callable[[], None],
        health_checks: Sequence[Callable[[], bool]] = (),
        recovery_checks: Sequence[Callable[[], bool]] = (),
        heartbeat_timeout_seconds: int = 15,
        max_restart_attempts: int = 3,
        restart_backoff_seconds: Sequence[int] = (1, 5, 15),
    ) -> None:
        if type(heartbeat_timeout_seconds) is not int or heartbeat_timeout_seconds < 1:
            raise ValueError("heartbeat_timeout_seconds must be a positive integer")
        if type(max_restart_attempts) is not int or max_restart_attempts < 0:
            raise ValueError("max_restart_attempts must be a non-negative integer")
        delays = tuple(restart_backoff_seconds)
        if not delays or any(type(delay) is not int or delay < 0 for delay in delays):
            raise ValueError("restart_backoff_seconds must contain non-negative integers")
        self._start_engine = start_engine
        self._stop_engine = stop_engine
        self._health_checks = tuple(health_checks)
        self._recovery_checks = tuple(recovery_checks)
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.max_restart_attempts = max_restart_attempts
        self.restart_backoff_seconds = delays
        self._lock = RLock()
        self._state = SupervisorState.STOPPED
        self._reason = "not_started"
        self._last_heartbeat: datetime | None = None
        self._next_restart_at: datetime | None = None
        self._restart_attempts = 0
        self._events: list[SupervisorEvent] = []

    @property
    def state(self) -> SupervisorState:
        with self._lock:
            return self._state

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def restart_attempts(self) -> int:
        with self._lock:
            return self._restart_attempts

    @property
    def last_heartbeat(self) -> datetime | None:
        with self._lock:
            return self._last_heartbeat

    @property
    def next_restart_at(self) -> datetime | None:
        with self._lock:
            return self._next_restart_at

    @property
    def events(self) -> tuple[SupervisorEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self._state.value,
                "reason": self._reason,
                "restart_attempts": self._restart_attempts,
                "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
                "next_restart_at": self._next_restart_at.isoformat() if self._next_restart_at else None,
            }

    def _transition(self, state: SupervisorState, reason: str, at: datetime) -> None:
        self._state = state
        self._reason = reason
        self._events.append(
            SupervisorEvent(state, at, reason, self._restart_attempts)
        )

    @staticmethod
    def _checks_pass(checks: Sequence[Callable[[], bool]]) -> bool:
        try:
            return all(check() is True for check in checks)
        except Exception:
            return False

    def _delay(self) -> int:
        index = min(self._restart_attempts, len(self.restart_backoff_seconds) - 1)
        return self.restart_backoff_seconds[index]

    def _schedule_retry(self, at: datetime, reason: str) -> None:
        if self._restart_attempts >= self.max_restart_attempts:
            self._next_restart_at = None
            self._transition(SupervisorState.HALTED, "restart_limit_exhausted:" + reason, at)
            return
        self._next_restart_at = at + timedelta(seconds=self._delay())
        self._transition(SupervisorState.DEGRADED, reason, at)

    def _stop_safely(self, at: datetime) -> bool:
        try:
            self._stop_engine()
            return True
        except Exception:
            self._next_restart_at = None
            self._transition(SupervisorState.HALTED, "engine_stop_failed_manual_intervention_required", at)
            return False

    def start(self, *, timestamp: datetime) -> bool:
        at = _aware(timestamp, "timestamp")
        with self._lock:
            if self._state != SupervisorState.STOPPED:
                return False
            self._transition(SupervisorState.STARTING, "startup_preflight", at)
            if not self._checks_pass(self._health_checks):
                self._transition(SupervisorState.HALTED, "startup_health_check_failed", at)
                return False
            if not self._checks_pass(self._recovery_checks):
                self._transition(SupervisorState.HALTED, "startup_reconciliation_failed", at)
                return False
            try:
                started = self._start_engine() is True
            except Exception:
                started = False
            if not started:
                self._schedule_retry(at, "initial_engine_start_failed")
                return False
            self._last_heartbeat = at
            self._next_restart_at = None
            self._transition(SupervisorState.RUNNING, "engine_started", at)
            return True

    def heartbeat(self, *, timestamp: datetime) -> None:
        at = _aware(timestamp, "timestamp")
        with self._lock:
            if self._state != SupervisorState.RUNNING:
                raise RuntimeError("heartbeat_rejected_engine_not_running")
            if self._last_heartbeat is not None and at <= self._last_heartbeat:
                raise ValueError("heartbeat timestamp must move forward")
            self._last_heartbeat = at

    def poll(self, *, timestamp: datetime) -> SupervisorState:
        """Detect a missed heartbeat or perform at most one due restart attempt."""
        at = _aware(timestamp, "timestamp")
        with self._lock:
            if self._state == SupervisorState.RUNNING:
                if self._last_heartbeat is None:
                    self._transition(SupervisorState.HALTED, "heartbeat_state_missing", at)
                    self._stop_safely(at)
                    return self._state
                age = (at - self._last_heartbeat).total_seconds()
                if age < 0:
                    self._transition(SupervisorState.HALTED, "supervisor_clock_moved_backwards", at)
                    self._stop_safely(at)
                    return self._state
                if age <= self.heartbeat_timeout_seconds:
                    if not self._checks_pass(self._health_checks):
                        self._transition(SupervisorState.DEGRADED, "runtime_health_check_failed", at)
                        if self._stop_safely(at):
                            self._schedule_retry(at, "runtime_health_check_failed")
                    return self._state
                self._transition(SupervisorState.DEGRADED, "heartbeat_timeout", at)
                if not self._stop_safely(at):
                    return self._state
                self._last_heartbeat = None
                self._schedule_retry(at, "heartbeat_timeout")
                return self._state

            if self._state != SupervisorState.DEGRADED:
                return self._state
            if self._next_restart_at is None or at < self._next_restart_at:
                return self._state

            if not self._checks_pass(self._recovery_checks):
                self._next_restart_at = None
                self._transition(SupervisorState.HALTED, "restart_reconciliation_failed", at)
                return self._state
            if not self._checks_pass(self._health_checks):
                self._restart_attempts += 1
                self._schedule_retry(at, "restart_health_check_failed")
                return self._state

            self._restart_attempts += 1
            try:
                started = self._start_engine() is True
            except Exception:
                started = False
            if not started:
                self._schedule_retry(at, "engine_restart_failed")
                return self._state

            self._last_heartbeat = at
            self._next_restart_at = None
            self._transition(SupervisorState.RUNNING, "engine_restarted_awaiting_healthy_heartbeat", at)
            return self._state

    def emergency_halt(self, *, timestamp: datetime, reason: str = "operator_emergency_halt") -> None:
        at = _aware(timestamp, "timestamp")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 256:
            raise ValueError("reason must contain 1 to 256 characters")
        with self._lock:
            if self._state == SupervisorState.HALTED:
                return
            self._next_restart_at = None
            self._transition(SupervisorState.HALTED, reason.strip(), at)
            self._stop_safely(at)

    def operator_reset(self, *, timestamp: datetime, reason: str) -> bool:
        """Clear only the in-memory supervisor latch after an explicit operator action.

        This does not clear the durable PaperAccountStore emergency-halt latch.
        That latch must be reconciled and reset through a separate audited procedure.
        """
        at = _aware(timestamp, "timestamp")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("operator reset requires a non-empty reason")
        with self._lock:
            if self._state != SupervisorState.HALTED:
                return False
            if not self._checks_pass(self._health_checks) or not self._checks_pass(self._recovery_checks):
                return False
            self._restart_attempts = 0
            self._last_heartbeat = None
            self._next_restart_at = None
            self._transition(SupervisorState.STOPPED, "operator_reset:" + reason.strip(), at)
            return True
