"""Offline provider event adapter and bounded feed reconnect state machine.

This is a deterministic test seam. The caller supplies a provider-specific
decoder, transport, authentication, subscription and session calendar.
No API credentials, sockets, threads, timers or order endpoints are used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable

from tradingbot.models import Bar
from tradingbot.runtime.paper_feed import PaperFeedRunner


class FeedState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    RECOVERING = "RECOVERING"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class FeedStatus:
    state: FeedState
    reason: str
    reconnect_attempts: int
    next_attempt_at: datetime | None
    last_bar_at: datetime | None


def _utc(at: datetime) -> datetime:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timestamp_must_be_timezone_aware")
    return at.astimezone(timezone.utc)


class OfflineFeedCoordinator:
    """No automatic retry of data gaps, ambiguous orders or account failures.

    connect() and reconnect() return *permission to attempt* a provider
    connection. They do not perform a connection. A caller must explicitly
    confirm connection, subscription and source-gap reconciliation.
    """

    def __init__(
        self,
        *,
        runner: PaperFeedRunner,
        decode_closed_bar: Callable[[object], Bar],
        max_reconnect_attempts: int = 3,
        backoff_seconds: tuple[int, ...] = (1, 5, 15),
    ) -> None:
        if not isinstance(runner, PaperFeedRunner):
            raise TypeError("paper_feed_runner_required")
        if not callable(decode_closed_bar):
            raise TypeError("closed_bar_decoder_required")
        if type(max_reconnect_attempts) is not int or max_reconnect_attempts < 0:
            raise ValueError("max_reconnect_attempts_invalid")
        if not backoff_seconds or any(type(n) is not int or n < 0 for n in backoff_seconds):
            raise ValueError("backoff_seconds_invalid")
        self.runner = runner
        self.decoder = decode_closed_bar
        self.max_reconnect_attempts = max_reconnect_attempts
        self.backoff_seconds = tuple(backoff_seconds)
        self.state = FeedState.DISCONNECTED
        self.reason = "not_connected"
        self.attempts = 0
        self.next_attempt_at: datetime | None = None
        self.last_bar_at: datetime | None = None

    def status(self) -> FeedStatus:
        return FeedStatus(self.state, self.reason, self.attempts, self.next_attempt_at, self.last_bar_at)

    def request_connect(self, *, at: datetime, preflight_approved: bool) -> bool:
        _utc(at)
        if self.state != FeedState.DISCONNECTED:
            return False
        if preflight_approved is not True or not self.runner.inbox.health().ready:
            self.state, self.reason = FeedState.HALTED, "startup_preflight_failed"
            return False
        self.state, self.reason = FeedState.CONNECTING, "awaiting_provider_confirmation"
        return True

    def confirm_connected(self, *, at: datetime, subscribed: bool, source_reconciled: bool) -> None:
        _utc(at)
        if self.state != FeedState.CONNECTING:
            raise RuntimeError("feed_not_connecting")
        if subscribed is not True or source_reconciled is not True:
            self.state, self.reason = FeedState.HALTED, "subscription_or_source_reconciliation_failed"
            raise RuntimeError(self.reason)
        if not self.runner.inbox.health().ready:
            self.state, self.reason = FeedState.HALTED, "inbox_not_ready"
            raise RuntimeError(self.reason)
        self.state, self.reason = FeedState.ACTIVE, "connected_and_reconciled"
        self.next_attempt_at = None

    def receive(self, event: object, *, received_at: datetime) -> int:
        at = _utc(received_at)
        if self.state != FeedState.ACTIVE:
            raise RuntimeError("feed_not_active")
        try:
            bar = self.decoder(event)
            if not isinstance(bar, Bar):
                raise TypeError("decoder_must_return_bar")
            event_id = self.runner.ingest(bar, received_at=at)
        except Exception:
            self.state, self.reason = FeedState.HALTED, "feed_decode_or_ingestion_failed"
            raise
        self.last_bar_at = at
        return event_id

    def on_disconnect(self, *, at: datetime, reason: str) -> None:
        now = _utc(at)
        if self.state != FeedState.ACTIVE:
            raise RuntimeError("disconnect_requires_active_feed")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("disconnect_reason_required")
        self.state, self.reason = FeedState.RECOVERING, reason.strip()[:256]
        self.attempts = 0
        self.next_attempt_at = now + timedelta(seconds=self.backoff_seconds[0])

    def request_reconnect(self, *, at: datetime, preflight_approved: bool) -> bool:
        now = _utc(at)
        if self.state != FeedState.RECOVERING:
            return False
        if preflight_approved is not True or not self.runner.inbox.health().ready:
            self.state, self.reason = FeedState.HALTED, "reconnect_preflight_failed"
            self.next_attempt_at = None
            return False
        if self.next_attempt_at is None or now < self.next_attempt_at:
            return False
        if self.attempts >= self.max_reconnect_attempts:
            self.state, self.reason = FeedState.HALTED, "reconnect_limit_exhausted"
            self.next_attempt_at = None
            return False
        self.attempts += 1
        self.state, self.reason = FeedState.CONNECTING, "awaiting_provider_reconnect_confirmation"
        self.next_attempt_at = None
        return True

    def reconnect_failed(self, *, at: datetime) -> None:
        now = _utc(at)
        if self.state != FeedState.CONNECTING or self.attempts < 1:
            raise RuntimeError("reconnect_failure_not_expected")
        if self.attempts >= self.max_reconnect_attempts:
            self.state, self.reason = FeedState.HALTED, "reconnect_limit_exhausted"
            return
        delay = self.backoff_seconds[min(self.attempts, len(self.backoff_seconds) - 1)]
        self.state, self.reason = FeedState.RECOVERING, "provider_reconnect_failed"
        self.next_attempt_at = now + timedelta(seconds=delay)

    def halt(self, *, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("halt_reason_required")
        self.state, self.reason = FeedState.HALTED, reason.strip()[:256]
        self.next_attempt_at = None
