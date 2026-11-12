"""Fail-closed session lifecycle for short-horizon paper trading.

This module deliberately has no broker, network, scheduler or live-order access.
It coordinates already-closed bars and delegates decisions to an injected handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class SessionState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    READY = "READY"
    RUNNING = "RUNNING"
    EXITING = "EXITING"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class SessionEvent:
    state: SessionState
    timestamp: datetime
    reason: str


class SessionController(Generic[T]):
    """Serial, idempotent closed-bar dispatcher with latched fail-closed states.

    The handler is expected to perform deterministic strategy evaluation, risk
    checks and paper execution. Exceptions degrade the session and block later
    bars until an operator performs an explicit recovery sequence.
    """

    def __init__(
        self,
        *,
        on_closed_bar: Callable[[T], None],
        timestamp_of: Callable[[T], datetime],
        startup_checks: tuple[Callable[[], bool], ...] = (),
        max_hold_seconds: int = 900,
    ) -> None:
        if type(max_hold_seconds) is not int or not 1 <= max_hold_seconds <= 900:
            raise ValueError("max_hold_seconds must be an integer from 1 to 900")
        self._on_closed_bar = on_closed_bar
        self._timestamp_of = timestamp_of
        self._startup_checks = startup_checks
        self.max_hold_seconds = max_hold_seconds
        self._lock = RLock()
        self._state = SessionState.STOPPED
        self._last_bar_timestamp: datetime | None = None
        self._events: list[SessionEvent] = []
        self._reason = "not_started"

    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def last_bar_timestamp(self) -> datetime | None:
        with self._lock:
            return self._last_bar_timestamp

    @property
    def events(self) -> tuple[SessionEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def _transition(self, state: SessionState, reason: str, timestamp: datetime) -> None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Session event timestamp must be timezone-aware")
        self._state = state
        self._reason = reason
        self._events.append(SessionEvent(state, timestamp, reason))

    def start(self, *, timestamp: datetime) -> bool:
        with self._lock:
            if self._state not in (SessionState.STOPPED,):
                return False
            self._transition(SessionState.STARTING, "startup_checks_running", timestamp)
            try:
                if not all(check() is True for check in self._startup_checks):
                    self._transition(SessionState.DEGRADED, "startup_check_failed", timestamp)
                    return False
            except Exception:
                self._transition(SessionState.DEGRADED, "startup_check_exception", timestamp)
                return False
            self._transition(SessionState.READY, "startup_checks_passed", timestamp)
            return True

    def begin(self, *, timestamp: datetime) -> bool:
        with self._lock:
            if self._state != SessionState.READY:
                return False
            self._transition(SessionState.RUNNING, "session_started", timestamp)
            return True

    def process_closed_bar(self, bar: T) -> bool:
        with self._lock:
            if self._state != SessionState.RUNNING:
                return False
            try:
                stamp = self._timestamp_of(bar)
                if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("closed_bar_timestamp_must_be_timezone_aware")
                if self._last_bar_timestamp is not None and stamp <= self._last_bar_timestamp:
                    self._transition(SessionState.DEGRADED, "duplicate_or_out_of_order_bar", stamp)
                    return False
                self._on_closed_bar(bar)
                self._last_bar_timestamp = stamp
                return True
            except Exception:
                stamp = self._last_bar_timestamp
                if stamp is None:
                    # Use the supplied timestamp only if it can safely be read.
                    try:
                        stamp = self._timestamp_of(bar)
                    except Exception:
                        stamp = None
                if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise
                self._transition(SessionState.DEGRADED, "closed_bar_handler_failed", stamp)
                return False

    def request_stop(self, *, timestamp: datetime, reason: str = "operator_stop") -> bool:
        with self._lock:
            if self._state not in (SessionState.RUNNING, SessionState.READY):
                return False
            self._transition(SessionState.EXITING, reason, timestamp)
            self._transition(SessionState.STOPPED, "entries_blocked_session_stopped", timestamp)
            return True

    def emergency_halt(self, *, timestamp: datetime, reason: str = "emergency_halt") -> None:
        with self._lock:
            if self._state == SessionState.HALTED:
                return
            self._transition(SessionState.HALTED, reason, timestamp)

    def reset_halt(self, *, timestamp: datetime, operator_reason: str) -> bool:
        with self._lock:
            if self._state != SessionState.HALTED or not operator_reason.strip():
                return False
            self._transition(SessionState.STOPPED, "halt_reset:" + operator_reason.strip(), timestamp)
            self._last_bar_timestamp = None
            return True
