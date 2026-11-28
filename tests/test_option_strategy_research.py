from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from dataclasses import replace

from tradingbot.research.option_replay import ReplaySnapshot
from tradingbot.research.option_signals import extract_features, CANDIDATES, Regime
from tradingbot.research.option_trials import trial, select_and_holdout
from tradingbot.risk.index_options import OptionQuote, Right

T = datetime(2026,11,26,5,tzinfo=timezone.utc)


def rows(n=500):
    out=[]
    for i in range(n):
        t=T+timedelta(seconds=i)
        q=OptionQuote(timestamp=t, underlying_timestamp=t, instrument_key="NSE_FO|100",
                      bid=D("99")+D(i)/10, ask=D("100")+D(i)/10,
                      bid_quantity=100, ask_quantity=100, underlying_price=D(25000+i),
                      implied_volatility=D(".2"), open_interest=1000)
        out.append(ReplaySnapshot(q,t,"fixture","fixture"))
    return tuple(out)


def test_features_ignore_future_and_distinguish_direction():
    r=rows()
    at=T+timedelta(seconds=60)
    f=extract_features(r,at=at,right=Right.CALL)
    assert f == extract_features(r[:61],at=at,right=Right.CALL)
    assert f.regime is Regime.TREND
    assert CANDIDATES[0].accepts(f)
    assert not CANDIDATES[0].accepts(extract_features(r,at=at,right=Right.PUT))


def test_gap_blocks_features():
    r=rows()
    assert extract_features(r[:20]+r[40:61],at=r[60].received_at,right=Right.CALL) is None


def test_trial_uses_later_ask_and_bid_and_costs():
    r=rows(370)
    a=trial(r,CANDIDATES[0],right=Right.CALL,quantity=65,fees=D(60))
    b=trial(r,CANDIDATES[0],right=Right.CALL,quantity=65,fees=D(100))
    assert a.performance.trades == b.performance.trades == 1
    assert a.performance.net_pnl-b.performance.net_pnl == D(40)


def test_missing_exit_is_not_counted_as_win():
    a=trial(rows(80),CANDIDATES[0],right=Right.CALL,quantity=65,fees=D(60))
    assert a.unresolved == 1
    assert a.performance is None


def test_insufficient_training_sample_blocks_selection():
    reports, held=select_and_holdout(rows(),right=Right.CALL,quantity=65,fees=D(60),
                                   split_at=T+timedelta(seconds=400))
    assert len(reports)==3
    assert held is None
