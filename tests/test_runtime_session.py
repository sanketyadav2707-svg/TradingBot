from datetime import datetime, timedelta, timezone

from tradingbot.markets.nse_calendar import NSEMarketCalendar, NSESessionBarGuard\nfrom tradingbot.runtime.session import SessionController, SessionState

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



def test_nse_session_bar_guard_allows_regular_continuous_session_bar() -> None:
    seen = []
    guard = NSESessionBarGuard(
        calendar=NSEMarketCalendar(),
        segment="equity_derivatives",
        timestamp_of=lambda bar: bar["timestamp"],
    )
    session = SessionController(
        on_closed_bar=seen.append,
        timestamp_of=lambda bar: bar["timestamp"],
        bar_checks=(guard,),
    )
    now = datetime(2026, 11, 16, 4, 0, tzinfo=UTC)  # 09:30 IST
    assert session.start(timestamp=now)
    assert session.begin(timestamp=now)
    bar = {"timestamp": now + timedelta(minutes=1)}
    assert session.process_closed_bar(bar)
    assert seen == [bar]


def test_nse_session_bar_guard_blocks_after_close_and_latches_degraded() -> None:
    seen = []
    guard = NSESessionBarGuard(
        calendar=NSEMarketCalendar(),
        segment="equity",
        timestamp_of=lambda bar: bar["timestamp"],
    )
    session = SessionController(
        on_closed_bar=seen.append,
        timestamp_of=lambda bar: bar["timestamp"],
        bar_checks=(guard,),
    )
    start = datetime(2026, 11, 16, 4, 0, tzinfo=UTC)
    assert session.start(timestamp=start)
    assert session.begin(timestamp=start)
    after_close = {"timestamp": datetime(2026, 11, 16, 10, 1, tzinfo=UTC)}  # 15:31 IST
    assert session.process_closed_bar(after_close) is False
    assert session.state == SessionState.DEGRADED
    assert session.reason == "closed_bar_session_check_failed"
    assert seen == []


def test_nse_session_bar_guard_fails_closed_on_unverified_calendar_date() -> None:
    guard = NSESessionBarGuard(
        calendar=NSEMarketCalendar(),
        segment="equity_derivatives",
        timestamp_of=lambda bar: bar["timestamp"],
    )
    session = SessionController(
        on_closed_bar=lambda bar: None,
        timestamp_of=lambda bar: bar["timestamp"],
        bar_checks=(guard,),
    )
    start = datetime(2027, 1, 4, 4, 0, tzinfo=UTC)
    assert session.start(timestamp=start)
    assert session.begin(timestamp=start)
    assert session.process_closed_bar({"timestamp": start}) is False
    assert session.state == SessionState.DEGRADED


def test_nse_expiring_index_contract_guard_uses_shorter_early_close() -> None:
    guard = NSESessionBarGuard(
        calendar=NSEMarketCalendar(),
        segment="equity_derivatives",
        timestamp_of=lambda bar: bar["timestamp"],
        expiring_index_derivative=True,
    )
    session = SessionController(
        on_closed_bar=lambda bar: None,
        timestamp_of=lambda bar: bar["timestamp"],
        bar_checks=(guard,),
    )
    start = datetime(2026, 12, 8, 4, 0, tzinfo=UTC)
    assert session.start(timestamp=start)
    assert session.begin(timestamp=start)
    after_expiry_close = {"timestamp": datetime(2026, 12, 8, 10, 5, tzinfo=UTC)}  # 15:35 IST
    assert session.process_closed_bar(after_expiry_close) is False
    assert session.state == SessionState.DEGRADED
