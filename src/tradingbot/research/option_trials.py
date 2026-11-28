"""Offline next-quote execution research and chronological candidate selection."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal as D

from tradingbot.research.option_signals import CANDIDATES, Strategy, extract_features
from tradingbot.research.option_replay import ReplaySnapshot
from tradingbot.risk.index_options import Right, aware, decimal
from tradingbot.research.option_performance import evaluate_option_performance, OptionPerformance


@dataclass(frozen=True)
class Trial:
    strategy: str
    performance: OptionPerformance | None
    unresolved: int
    signals: int


def trial(rows: tuple[ReplaySnapshot, ...], strategy: Strategy, *, right: Right,
          quantity: int, fees: D, holding_seconds: int = 300,
          slippage: D = D("0.05")) -> Trial:
    """Independent fixed-quantity research trial, not an account backtest."""
    fees, slippage = decimal(fees, "fees"), decimal(slippage, "slippage")
    if type(quantity) is not int or quantity < 1 or fees < 0 or slippage < 0:
        raise ValueError("invalid_trial_economics")
    if type(holding_seconds) is not int or not 180 <= holding_seconds <= 900:
        raise ValueError("invalid_holding_window")
    times = [aware(r.received_at, "receipt") for r in rows]
    if any(b <= a for a,b in zip(times,times[1:])):
        raise ValueError("unordered_trial")
    if len({(r.quote.instrument_key,r.source_id) for r in rows}) > 1:
        raise ValueError("mixed_trial_identity")
    pnls = []
    unresolved = signals = 0
    i = 0
    def executable(j, side):
        q = rows[j].quote
        return (not q.trading_halted and
                timedelta(0) <= times[j]-aware(q.timestamp,"quote") <= timedelta(seconds=2)
                and getattr(q,side+"_quantity") >= quantity)
    while i+1 < len(rows):
        f = extract_features(rows[max(0,i-2000):i+1], at=times[i], right=right)
        if f is None or not strategy.accepts(f):
            i += 1
            continue
        signals += 1
        j = i+1
        if times[j]-times[i] > timedelta(seconds=2) or not executable(j,"ask"):
            i += 1
            continue
        entry = rows[j].quote.ask + slippage
        deadline = times[j]+timedelta(seconds=holding_seconds)
        k = j+1
        closed = False
        while k < len(rows):
            q = rows[k].quote
            if times[k]-times[k-1] > timedelta(seconds=10) or q.trading_halted:
                break
            if q.bid <= entry*D(".85") or q.bid >= entry*D("1.30") or times[k]>=deadline:
                if executable(k,"bid") and q.bid > 0:
                    pnls.append((max(D(0),q.bid-slippage)-entry)*quantity-fees)
                    closed = True
                    break
            k += 1
        if not closed:
            unresolved += 1
            break
        i = k+1
    return Trial(strategy.name, evaluate_option_performance(tuple(pnls)) if pnls else None,
                 unresolved, signals)


def select_and_holdout(rows, *, right, quantity, fees, split_at,
                       candidates=CANDIDATES, min_trades=30):
    """Select on earlier receipts only; evaluate one frozen candidate later."""
    cutoff = aware(split_at,"split")
    train = tuple(r for r in rows if aware(r.received_at,"receipt") < cutoff)
    test = tuple(r for r in rows if aware(r.received_at,"receipt") >= cutoff)
    results = [(s,trial(train,s,right=right,quantity=quantity,fees=fees)) for s in candidates]
    eligible = [(s,r) for s,r in results if not r.unresolved and r.performance
                and r.performance.trades >= min_trades and r.performance.net_pnl > 0]
    if not eligible:
        return tuple(r for _,r in results), None
    winner,_ = max(eligible,key=lambda x:x[1].performance.expectancy_per_trade)
    return tuple(r for _,r in results), trial(test,winner,right=right,quantity=quantity,fees=fees)
