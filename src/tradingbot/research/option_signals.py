"""Causal option features and competing research strategies.

All features use only snapshots received by the decision time. Signals are
research hypotheses, not risk approvals. No broker or order router is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal as D
from enum import Enum
from math import sqrt

from tradingbot.research.option_replay import ReplaySnapshot
from tradingbot.risk.index_options import Right, aware


class Regime(str, Enum):
    TREND = "trend"
    RANGE = "range"
    SHOCK = "shock"


@dataclass(frozen=True, slots=True)
class Features:
    at: datetime
    direction_return: D
    prior_direction_return: D
    premium_return: D
    iv_change: D
    spread_fraction: D
    efficiency: D
    realized_volatility: float
    regime: Regime


def extract_features(
    history: tuple[ReplaySnapshot, ...], *, at: datetime, right: Right,
    lookback_seconds: int = 60, max_age_seconds: int = 2,
    max_gap_seconds: int = 10,
) -> Features | None:
    now = aware(at, "decision")
    if not isinstance(right, Right):
        raise ValueError("invalid_option_right")
    if any(type(x) is not int or x < 1 for x in
           (lookback_seconds, max_age_seconds, max_gap_seconds)):
        raise ValueError("invalid_feature_window")
    if lookback_seconds < 2 * max_gap_seconds:
        raise ValueError("feature_window_too_short")
    start = now - timedelta(seconds=lookback_seconds)
    rows = [r for r in history if start <= aware(r.received_at, "receipt") <= now]
    if len(rows) < 5:
        return None
    key = (rows[0].quote.instrument_key, rows[0].source_id)
    prev = None
    for r in rows:
        received = aware(r.received_at, "receipt")
        q = r.quote
        if (q.instrument_key, r.source_id) != key:
            raise ValueError("mixed_feature_identity")
        if prev is not None and received <= prev:
            raise ValueError("unordered_feature_receipts")
        if prev is not None and received - prev > timedelta(seconds=max_gap_seconds):
            return None
        if q.trading_halted or q.bid <= 0:
            return None
        for stamp in (q.timestamp, q.underlying_timestamp):
            age = received - aware(stamp, "quote")
            if not timedelta(0) <= age <= timedelta(seconds=max_age_seconds):
                return None
        prev = received
    if aware(rows[0].received_at, "receipt") - start > timedelta(seconds=max_gap_seconds):
        return None
    if now - aware(rows[-1].received_at, "receipt") > timedelta(seconds=max_age_seconds):
        return None
    q0, q1 = rows[0].quote, rows[-1].quote
    if any(now - aware(t, "quote") > timedelta(seconds=max_age_seconds)
           for t in (q1.timestamp, q1.underlying_timestamp)):
        return None
    prices = [r.quote.underlying_price for r in rows]
    changes = [b-a for a,b in zip(prices, prices[1:])]
    path = sum(map(abs, changes), D(0))
    efficiency = abs(prices[-1]-prices[0])/path if path else D(0)
    direction = D(1) if right is Right.CALL else D(-1)
    ret = direction*(prices[-1]/prices[0]-1)
    mid = prices[len(prices)//2]
    prior = direction*(mid/prices[0]-1)
    iv = q1.implied_volatility/q0.implied_volatility-1
    premium = (q1.bid+q1.ask)/(q0.bid+q0.ask)-1
    vol = sqrt(sum(float(b/a-1)**2 for a,b in zip(prices,prices[1:])))
    regime = (Regime.SHOCK if abs(iv) > D(".15") or abs(ret) > D(".01")
              else Regime.TREND if efficiency >= D(".65") and abs(ret) >= D(".0005")
              else Regime.RANGE)
    return Features(now, ret, prior, premium, iv, (q1.ask-q1.bid)/q1.ask,
                    efficiency, vol, regime)


@dataclass(frozen=True, slots=True)
class Strategy:
    name: str
    min_direction_return: D
    min_premium_return: D
    min_efficiency: D
    require_pullback: bool = False

    def accepts(self, f: Features) -> bool:
        if f.regime is not Regime.TREND or f.spread_fraction > D(".015"):
            return False
        if f.iv_change < D("-.05"):
            return False
        if self.require_pullback and not D(0) < f.prior_direction_return < f.direction_return:
            return False
        return (f.direction_return >= self.min_direction_return
                and f.premium_return >= self.min_premium_return
                and f.efficiency >= self.min_efficiency)


CANDIDATES = (
    Strategy("momentum", D(".0005"), D(".005"), D(".65")),
    Strategy("selective_momentum", D(".001"), D(".01"), D(".8")),
    Strategy("continuation", D(".0007"), D(".005"), D(".7"), True),
)
