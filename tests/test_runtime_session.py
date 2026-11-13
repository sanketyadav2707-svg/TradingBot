from datetime import datetime, timedelta, timezone

from tradingbot.runtime.session import SessionController, SessionState

UTC = timezone.utc
T0 = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)


def test_session_requires_successful_startup_before_running() -> None:
    seen = []
    session = SessionController(
        on_closed_bar=seen.append,
        timestamp_of=lambda bar: bar["timestamp"],
        startup_checks=(lambda: True, lambda: False),
    )
    assert session.start(timestamp=T0) is False
    assert session.state == SessionState.DEGRADED
    assert session.begin(timestamp=T0) is False
    assert session.process_closed_bar({"timestamp": T0}) is False
    assert seen == []


def test_session_processes_only_monotonic_closed_bars() -> None:
    seen = []
    session = SessionController(
        on_closed_bar=seen.append,
        timestamp_of=lambda bar: bar["timestamp"],
    )
    assert session.start(timestamp=T0)
    assert session.begin(timestamp=T0)
    first = {"timestamp": T0 + timedelta(minutes=1)}
    assert session.process_closed_bar(first)
    assert seen == [first]
    assert session.process_closed_bar(first) is False
    assert session.state == SessionState.DEGRADED
    assert session.process_closed_bar({"timestamp": T0 + timedelta(minutes=2)}) is False
    assert len(seen) == 1


def test_handler_exception_degrades_and_blocks_following_bars() -> None:
    calls = []

    def handler(bar):
        calls.append(bar)
        raise RuntimeError("paper broker persistence failed")

    session = SessionController(
        on_closed_bar=handler,
        timestamp_of=lambda bar: bar["timestamp"],
    )
    assert session.start(timestamp=T0)
    assert session.begin(timestamp=T0)
    bar = {"timestamp": T0 + timedelta(minutes=1)}
    assert session.process_closed_bar(bar) is False
    assert session.state == SessionState.DEGRADED
    assert session.process_closed_bar({"timestamp": T0 + timedelta(minutes=2)}) is False
    assert calls == [bar]


def test_emergency_halt_is_latched_until_explicit_operator_reset() -> None:
    session = SessionController(
        on_closed_bar=lambda bar: None,
        timestamp_of=lambda bar: bar["timestamp"],
    )
    assert session.start(timestamp=T0)
    assert session.begin(timestamp=T0)
    session.emergency_halt(timestamp=T0 + timedelta(seconds=1))
    assert session.state == SessionState.HALTED
    assert session.begin(timestamp=T0 + timedelta(seconds=2)) is False
    assert session.reset_halt(
        timestamp=T0 + timedelta(seconds=3),
        operator_reason="feed restored and account reconciled",
    )
    assert session.state == SessionState.STOPPED


def test_holding_time_ceiling_cannot_exceed_fifteen_minutes() -> None:
    SessionController(
        on_closed_bar=lambda bar: None,
        timestamp_of=lambda bar: bar["timestamp"],
        max_hold_seconds=900,
    )
    try:
        SessionController(
            on_closed_bar=lambda bar: None,
            timestamp_of=lambda bar: bar["timestamp"],
            max_hold_seconds=901,
        )
    except ValueError as exc:
        assert "from 1 to 900" in str(exc)
    else:
        raise AssertionError("Expected >15 minute holding ceiling to be rejected")
