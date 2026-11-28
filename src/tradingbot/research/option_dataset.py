"""Causal, cost-aware training samples from one verified replay stream.

Labels are hypothetical independent trades, not account-level results.
Missing exits are counted separately, never silently converted to wins.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal as D

from tradingbot.research.option_greeks import calculate_greeks
from tradingbot.research.option_ml import Sample
from tradingbot.research.option_replay import ReplaySnapshot
from tradingbot.research.option_signals import CANDIDATES, extract_features
from tradingbot.risk.index_options import OptionContract, aware, decimal

FEATURE_NAMES = (
    "direction_return", "prior_direction_return", "premium_return", "iv_change",
    "spread_fraction", "efficiency", "realized_volatility", "delta", "gamma",
    "theta_relative", "vega_relative", "days_to_expiry", "depth_imbalance",
)


@dataclass(frozen=True, slots=True)
class Dataset:
    samples: tuple[Sample, ...]
    unresolved: int
    rejected_entries: int
    feature_names: tuple[str, ...] = FEATURE_NAMES


def build_dataset(
    rows: tuple[ReplaySnapshot, ...], *, contract: OptionContract,
    expiry_at: datetime, rate: float, dividend: float, fees: D,
    holding_seconds: int = 300, slippage: D = D("0.05"),
) -> Dataset:
    """Use one lot and disjoint labeled trade intervals per contract.

    Contract metadata and expiry instant must be supplied from dated sources.
    Stops/targets are experimental and use executable bid, never theoretical price.
    """
    expiry = aware(expiry_at, "expiry")
    if expiry_at.date() != contract.expiry:
        raise ValueError("expiry_date_mismatch")
    fees, slippage = decimal(fees, "fees"), decimal(slippage, "slippage")
    if fees < 0 or slippage < 0 or type(holding_seconds) is not int or not 180 <= holding_seconds <= 900:
        raise ValueError("invalid_dataset_economics")
    times = [aware(r.received_at, "receipt") for r in rows]
    if any(b <= a for a,b in zip(times,times[1:])):
        raise ValueError("unordered_dataset")
    if any(r.quote.instrument_key != contract.instrument_key for r in rows) or len({r.source_id for r in rows})>1:
        raise ValueError("mixed_dataset_identity")
    qty = contract.lot_size
    result=[]; unresolved=0; rejected=0; i=0
    def valid(j, side):
        q=rows[j].quote
        return (times[j]<expiry and not q.trading_halted and
                timedelta(0)<=times[j]-aware(q.timestamp,"quote")<=timedelta(seconds=2)
                and getattr(q,side+"_quantity")>=qty)
    while i+1<len(rows):
        at=times[i]
        f=extract_features(rows[max(0,i-2000):i+1],at=at,right=contract.right)
        candidates=[s for s in CANDIDATES if f is not None and s.accepts(f)]
        if not candidates or at+timedelta(seconds=holding_seconds+2)>=expiry:
            i+=1; continue
        if aware(contract.master_verified_at,"master")>at:
            i+=1; continue
        q=rows[i].quote
        days=(expiry-at).total_seconds()/86400
        g=calculate_greeks(spot=float(q.underlying_price),strike=float(contract.strike),
                           years=days/365,volatility=float(q.implied_volatility),
                           rate=rate,dividend=dividend,right=contract.right)
        mid=float((q.bid+q.ask)/2)
        features=tuple(map(float,(f.direction_return,f.prior_direction_return,f.premium_return,
                    f.iv_change,f.spread_fraction,f.efficiency,f.realized_volatility,
                    g.delta,g.gamma,g.theta_per_day/mid,g.vega_per_point/mid,days,
                    (q.bid_quantity-q.ask_quantity)/max(1,q.bid_quantity+q.ask_quantity))))
        j=i+1
        if times[j]-at>timedelta(seconds=2) or not valid(j,"ask"):
            rejected+=1; i+=1; continue
        entry=rows[j].quote.ask+slippage
        deadline=times[j]+timedelta(seconds=holding_seconds)
        k=j+1; closed=False
        while k<len(rows):
            exitq=rows[k].quote
            if times[k]-times[k-1]>timedelta(seconds=10) or exitq.trading_halted or times[k]>=expiry:
                break
            if exitq.bid<=entry*D(".85") or exitq.bid>=entry*D("1.30") or times[k]>=deadline:
                if valid(k,"bid") and exitq.bid>0:
                    pnl=(max(D(0),exitq.bid-slippage)-entry)*qty-fees
                    for strategy in candidates:
                        result.append(Sample(at,times[k],features,float(pnl),strategy.name))
                    closed=True; break
            k+=1
        if not closed:
            unresolved+=1
            break
        i=k+1
    return Dataset(tuple(result),unresolved,rejected)
