from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from dataclasses import replace
import pytest
from tradingbot.research.option_dataset import build_dataset
from tradingbot.research.option_replay import ReplaySnapshot
from tradingbot.research.option_ml import Sample
from tradingbot.research.option_walk_forward import walk_forward
from tradingbot.paper.durable_index_options import DurableOptionPaper
from tradingbot.risk.index_options import OptionContract,OptionQuote,OptionAccount,OptionRiskPolicy,Right,evaluate_long_option_entry

T=datetime(2026,11,26,5,tzinfo=timezone.utc)
def contract():
    return OptionContract("NSE_FO|100","NIFTY","NSE",Right.CALL,D(25000),
                          T.date()+timedelta(days=5),65,D(".05"),1800,T-timedelta(hours=1),
                          "https://www.nseindia.com")
def quotes(n):
    return tuple(ReplaySnapshot(OptionQuote(timestamp=T+timedelta(seconds=i),
        instrument_key="NSE_FO|100",bid=D(99)+D(i)/10,ask=D(100)+D(i)/10,
        bid_quantity=100,ask_quantity=100,underlying_price=D(25000+i),
        underlying_timestamp=T+timedelta(seconds=i),implied_volatility=D(".2"),
        open_interest=1000),T+timedelta(seconds=i),"fixture","fixture") for i in range(n))

def test_dataset_cost_and_features():
    args=dict(contract=contract(),expiry_at=T+timedelta(days=5),rate=.05,dividend=0)
    rows=quotes(370)
    a=build_dataset(rows,fees=D(60),**args)
    b=build_dataset(rows,fees=D(100),**args)
    assert a.samples and len(a.samples[0].features)==13
    assert a.samples[0].net_pnl-b.samples[0].net_pnl==pytest.approx(40)
    assert all(s.label_end>s.at for s in a.samples)

def test_unresolved_outcome_not_a_training_label():
    d=build_dataset(quotes(80),contract=contract(),expiry_at=T+timedelta(days=5),
                    rate=.05,dividend=0,fees=D(60))
    assert d.unresolved==1 and not d.samples

def test_walk_forward_uses_frozen_later_folds():
    rows=tuple(Sample(T+timedelta(minutes=3*i),T+timedelta(minutes=3*i+1),
                 (float(i%2),),100 if i%2 else -50,"momentum") for i in range(200))
    folds=walk_forward(rows,boundaries=tuple(T+timedelta(minutes=3*i) for i in (100,150,200)),
                       strategy="momentum",min_train=90,min_test=40)
    assert len(folds)==2
    assert all(f.report.brier<f.report.baseline_brier and f.report.net_pnl>0 for f in folds)
    with pytest.raises(ValueError,match="overlapping"):
        walk_forward(rows+(rows[0],),boundaries=(T+timedelta(minutes=300),T+timedelta(minutes=600)),
                     strategy="momentum")

def test_paper_restart_preserves_position_and_halt(tmp_path):
    path=tmp_path/"paper.db"
    c=contract(); q=quotes(1)[0].quote
    a=OptionAccount(D(1000000),D(100000),D(0),D(1000000),D(0),0,0,0,False,True)
    decision=evaluate_long_option_entry(now=T,contract=c,quote=q,account=a,
        policy=OptionRiskPolicy(),lots=1,round_trip_fees_rupees=D(60),
        official_session_verified=True,data_feed_healthy=True,
        option_master_matches_quote=True,broker_permissions_verified=True)
    assert decision.approved
    first=DurableOptionPaper(path)
    first.enter(decision=decision,contract=c,quote=q)
    second=DurableOptionPaper(path)
    assert second.snapshot().position.quantity==65
    with pytest.raises(RuntimeError,match="unreliable"):
        second.evaluate_exit(quote=q,now=T+timedelta(minutes=5))
    third=DurableOptionPaper(path)
    assert third.snapshot().halted and third.snapshot().position is not None
    with pytest.raises(ValueError,match="configuration"):
        DurableOptionPaper(path,max_holding_seconds=300)

def test_paper_exit_pnl_persists(tmp_path):
    path=tmp_path/"paper.db"
    c=contract(); q=quotes(1)[0].quote
    a=OptionAccount(D(1000000),D(100000),D(0),D(1000000),D(0),0,0,0,False,True)
    decision=evaluate_long_option_entry(now=T,contract=c,quote=q,account=a,
        policy=OptionRiskPolicy(),lots=1,round_trip_fees_rupees=D(60),
        official_session_verified=True,data_feed_healthy=True,
        option_master_matches_quote=True,broker_permissions_verified=True)
    paper=DurableOptionPaper(path)
    paper.enter(decision=decision,contract=c,quote=q)
    later=replace(q,timestamp=T+timedelta(seconds=1),bid=D(131),ask=D(132))
    exit=paper.evaluate_exit(quote=later,now=later.timestamp)
    restored=DurableOptionPaper(path).snapshot()
    assert restored.position is None and restored.realized_pnl==exit.net_pnl
