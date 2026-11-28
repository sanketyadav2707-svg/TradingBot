"""Fail-closed market-regime and operational conditions for bought index options.

An external verified market/event feed must supply this snapshot. A caller
cannot infer scheduled-news coverage from missing events. No market prediction
or live-broker integration is implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise ValueError(name + "_must_be_exact_decimal")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(name + "_invalid") from exc
    if not d.is_finite():
        raise ValueError(name + "_nonfinite")
    return d


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(name + "_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class OptionMarketConditions:
    observed_at: datetime
    event_calendar_checked_at: datetime
    next_or_recent_high_impact_event_at: datetime | None
    event_calendar_verified: bool
    market_state: str
    volatility_regime: str
    iv_change_5m_fraction: Decimal
    underlying_move_1m_fraction: Decimal
    round_trip_latency_ms: int
    quote_feed_recovered: bool
    broker_session_healthy: bool
    exchange_order_eligibility_verified: bool
    consecutive_losses: int
    last_loss_at: datetime | None

    def __post_init__(self) -> None:
        _utc(self.observed_at, "observed_at")
        _utc(self.event_calendar_checked_at, "event_calendar_checked_at")
        if self.next_or_recent_high_impact_event_at is not None:
            _utc(self.next_or_recent_high_impact_event_at, "event_time")
        if self.last_loss_at is not None:
            _utc(self.last_loss_at, "last_loss_at")
        for field in ("event_calendar_verified", "quote_feed_recovered",
                      "broker_session_healthy", "exchange_order_eligibility_verified"):
            if type(getattr(self, field)) is not bool:
                raise ValueError(field + "_must_be_bool")
        if self.market_state not in {"normal", "halted", "auction", "restricted", "unknown"}:
            raise ValueError("market_state_invalid")
        if self.volatility_regime not in {"normal", "elevated", "extreme", "unknown"}:
            raise ValueError("volatility_regime_invalid")
        for field in ("iv_change_5m_fraction", "underlying_move_1m_fraction"):
            object.__setattr__(self, field, _decimal(getattr(self, field), field))
        if type(self.round_trip_latency_ms) is not int or self.round_trip_latency_ms < 0:
            raise ValueError("round_trip_latency_invalid")
        if type(self.consecutive_losses) is not int or self.consecutive_losses < 0:
            raise ValueError("consecutive_losses_invalid")


@dataclass(frozen=True, slots=True)
class OptionConditionPolicy:
    max_snapshot_age_seconds: int = 3
    max_event_calendar_age_hours: int = 24
    event_blackout_minutes: int = 30
    max_abs_iv_change_5m_fraction: Decimal = Decimal("0.30")
    max_abs_underlying_move_1m_fraction: Decimal = Decimal("0.015")
    max_round_trip_latency_ms: int = 1500
    max_consecutive_losses: int = 2
    loss_cooldown_minutes: int = 20

    def __post_init__(self) -> None:
        for field in ("max_snapshot_age_seconds", "max_event_calendar_age_hours",
                      "event_blackout_minutes", "max_round_trip_latency_ms",
                      "max_consecutive_losses", "loss_cooldown_minutes"):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise ValueError(field + "_must_be_positive_integer")
        for field in ("max_abs_iv_change_5m_fraction", "max_abs_underlying_move_1m_fraction"):
            d = _decimal(getattr(self, field), field)
            if not Decimal("0") < d <= Decimal("1"):
                raise ValueError(field + "_out_of_range")
            object.__setattr__(self, field, d)


def reject_unsafe_option_conditions(
    *, now: datetime, conditions: OptionMarketConditions, policy: OptionConditionPolicy
) -> str | None:
    """Return a deterministic reason, or None when this layer permits entry."""
    instant = _utc(now, "now")
    if not isinstance(conditions, OptionMarketConditions) or not isinstance(policy, OptionConditionPolicy):
        raise TypeError("verified_conditions_and_policy_required")
    observed = _utc(conditions.observed_at, "observed_at")
    checked = _utc(conditions.event_calendar_checked_at, "event_calendar_checked_at")
    if observed > instant or checked > instant:
        return "future_dated_market_conditions"
    if instant - observed > timedelta(seconds=policy.max_snapshot_age_seconds):
        return "stale_market_conditions"
    if not conditions.event_calendar_verified:
        return "high_impact_event_calendar_unverified"
    if instant - checked > timedelta(hours=policy.max_event_calendar_age_hours):
        return "stale_high_impact_event_calendar"
    if conditions.market_state != "normal":
        return "exchange_market_state_not_normal"
    if conditions.volatility_regime in {"extreme", "unknown"}:
        return "volatility_regime_unsafe_or_unknown"
    if not conditions.quote_feed_recovered:
        return "quote_feed_recovery_incomplete"
    if not conditions.broker_session_healthy:
        return "broker_session_unhealthy"
    if not conditions.exchange_order_eligibility_verified:
        return "exchange_order_eligibility_unverified"
    if conditions.round_trip_latency_ms > policy.max_round_trip_latency_ms:
        return "broker_latency_too_high"
    if abs(conditions.iv_change_5m_fraction) > policy.max_abs_iv_change_5m_fraction:
        return "implied_volatility_spike_or_crush"
    if abs(conditions.underlying_move_1m_fraction) > policy.max_abs_underlying_move_1m_fraction:
        return "underlying_price_shock"
    event = conditions.next_or_recent_high_impact_event_at
    if event is not None and abs(instant - _utc(event, "event_time")) <= timedelta(minutes=policy.event_blackout_minutes):
        return "high_impact_event_blackout"
    if conditions.consecutive_losses >= policy.max_consecutive_losses:
        return "consecutive_loss_circuit_breaker"
    if conditions.last_loss_at is not None:
        last = _utc(conditions.last_loss_at, "last_loss_at")
        if last > instant:
            return "future_dated_last_loss"
        if instant - last < timedelta(minutes=policy.loss_cooldown_minutes):
            return "post_loss_cooldown_active"
    return None
