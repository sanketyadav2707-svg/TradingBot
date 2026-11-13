from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.runtime.supervisor import (
    EngineSupervisor,
    SupervisorState,
    timestamp_is_fresh,
)

UTC = timezone.utc
T0 = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)


def make_supervisor(**kwargs):
    calls = {"start": 0, "stop": 0}

    start_result = kwargs.pop("start_result", True)

    def start():
        calls["start"] += 1
        return start_result

    def stop():
        calls["stop"] += 1

    supervisor = EngineSupervisor(
        start_engine=start,
        stop_engine=stop,
        **kwargs,
    )
    return supervisor, calls


def test_start_requires_health_and_reconciliation_before_engine_start():
    started = []
    supervisor = EngineSupervisor(
        start_engine=lambda: started.append(True) or True,
        stop_engine=lambda: None,
        health_checks=(lambda: True,),
        recovery_checks=(lambda: False,),
    )
    assert supervisor.start(timestamp=T0) is False
    assert supervisor.state == SupervisorState.HALTED
    assert started == []


def test_healthy_heartbeat_keeps_engine_running():
    supervisor, calls = make_supervisor(heartbeat_timeout_seconds=10)
    assert supervisor.start(timestamp=T0)
    supervisor.heartbeat(timestamp=T0 + timedelta(seconds=5))
    assert supervisor.poll(timestamp=T0 + timedelta(seconds=14)) == SupervisorState.RUNNING
    assert calls["start"] == 1
    assert calls["stop"] == 0


def test_stale_heartbeat_stops_engine_and_schedules_bounded_restart():
    supervisor, calls = make_supervisor(
        heartbeat_timeout_seconds=10,
        max_restart_attempts=2,
        restart_backoff_seconds=(2, 5),
    )
    assert supervisor.start(timestamp=T0)
    assert supervisor.poll(timestamp=T0 + timedelta(seconds=11)) == SupervisorState.DEGRADED
    assert calls["stop"] == 1
    assert supervisor.next_restart_at == T0 + timedelta(seconds=13)
    assert supervisor.poll(timestamp=T0 + timedelta(seconds=12)) == SupervisorState.DEGRADED
    assert supervisor.poll(timestamp=T0 + timedelta(seconds=13)) == SupervisorState.RUNNING
    assert calls["start"] == 2
    assert supervisor.restart_attempts == 1


def test_reconciliation_failure_after_crash_latches_halt_without_restart():
    checks = {"reconciled": True}
    supervisor, calls = make_supervisor(
        heartbeat_timeout_seconds=2,
        recovery_checks=(lambda: checks["reconciled"],),
    )
    assert supervisor.start(timestamp=T0)
    assert supervisor.poll(timestamp=T0 + timedelta(seconds=3)) == SupervisorState.DEGRADED
    checks["reconciled"] = False
    state = supervisor.poll(timestamp=T0 + timedelta(seconds=4))
    assert state == SupervisorState.HALTED
    assert calls["start"] == 1
    assert calls["stop"] == 1


def test_restart_limit_exhaustion_halts_engine():
    supervisor, calls = make_supervisor(
        heartbeat_timeout_seconds=1,
        max_restart_attempts=2,
        restart_backoff_seconds=(0,),
        start_result=False,
    )
    # Initial start fails and schedules first retry.
    assert supervisor.start(timestamp=T0) is False
    assert supervisor.state == SupervisorState.DEGRADED
    assert supervisor.poll(timestamp=T0) == SupervisorState.DEGRADED
    assert supervisor.poll(timestamp=T0) == SupervisorState.HALTED
    assert supervisor.restart_attempts == 2
    assert calls["start"] == 3


def test_health_failure_during_runtime_stops_and_degrades():
    checks = {"healthy": True}
    supervisor, calls = make_supervisor(
        health_checks=(lambda: checks["healthy"],),
        restart_backoff_seconds=(1,),
    )
    assert supervisor.start(timestamp=T0)
    checks["healthy"] = False
    assert supervisor.poll(timestamp=T0 + timedelta(seconds=1)) == SupervisorState.DEGRADED
    assert calls["stop"] == 1


def test_stop_failure_latches_halt_and_prevents_restart():
    def stop():
        raise OSError("could not stop child process")

    supervisor = EngineSupervisor(
        start_engine=lambda: True,
        stop_engine=stop,
        heartbeat_timeout_seconds=1,
    )
    assert supervisor.start(timestamp=T0)
    assert supervisor.poll(timestamp=T0 + timedelta(seconds=2)) == SupervisorState.HALTED
    assert supervisor.next_restart_at is None


def test_emergency_halt_is_latched_until_operator_reset_checks_pass():
    checks = {"ok": True}
    supervisor, calls = make_supervisor(
        health_checks=(lambda: checks["ok"],),
        recovery_checks=(lambda: checks["ok"],),
    )
    assert supervisor.start(timestamp=T0)
    supervisor.emergency_halt(timestamp=T0 + timedelta(seconds=1), reason="operator_stop")
    assert supervisor.state == SupervisorState.HALTED
    checks["ok"] = False
    assert supervisor.operator_reset(
        timestamp=T0 + timedelta(seconds=2), reason="operator investigated"
    ) is False
    checks["ok"] = True
    assert supervisor.operator_reset(
        timestamp=T0 + timedelta(seconds=3), reason="feed and account reconciled"
    )
    assert supervisor.state == SupervisorState.STOPPED
    assert calls["stop"] == 1


def test_supervisor_rejects_naive_and_backwards_heartbeat_timestamps():
    supervisor, _ = make_supervisor()
    assert supervisor.start(timestamp=T0)
    with pytest.raises(ValueError, match="timezone-aware"):
        supervisor.heartbeat(timestamp=T0.replace(tzinfo=None))
    with pytest.raises(ValueError, match="must move forward"):
        supervisor.heartbeat(timestamp=T0)


def test_future_dated_and_stale_market_data_are_not_fresh():
    now = T0 + timedelta(seconds=10)
    assert timestamp_is_fresh(T0 + timedelta(seconds=5), now=now, max_age_seconds=10)
    assert not timestamp_is_fresh(T0 - timedelta(seconds=1), now=now, max_age_seconds=10)
    assert not timestamp_is_fresh(now + timedelta(seconds=1), now=now, max_age_seconds=10)
    assert not timestamp_is_fresh(None, now=now, max_age_seconds=10)


def test_snapshot_is_read_only_and_reports_operating_state():
    supervisor, _ = make_supervisor()
    assert supervisor.start(timestamp=T0)
    snapshot = supervisor.snapshot()
    assert snapshot["state"] == "RUNNING"
    assert snapshot["restart_attempts"] == 0
    snapshot["state"] = "HALTED"
    assert supervisor.snapshot()["state"] == "RUNNING"
