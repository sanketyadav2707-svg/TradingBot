from datetime import datetime,timedelta,timezone
import pytest
from tradingbot.research.option_greeks import calculate_greeks,reprice_shock
from tradingbot.research.option_ml import Sample,fit,validate,select_signal
from tradingbot.risk.index_options import Right

def test_greeks_parity_and_reference():
    args=dict(spot=100,strike=100,years=1,volatility=.2,rate=.05,dividend=0)
    c=calculate_greeks(**args,right=Right.CALL)
    p=calculate_greeks(**args,right=Right.PUT)
    assert c.price==pytest.approx(10.45058357)
    assert p.price==pytest.approx(5.57352602)
    assert c.delta-p.delta==pytest.approx(1)
    assert c.gamma==pytest.approx(p.gamma)
    assert c.vega_per_point==pytest.approx(.37524035)
    assert reprice_shock(**args,right=Right.CALL,spot_return=.1,iv_change=0,elapsed_seconds=365*86400)==pytest.approx(10)

def test_invalid_greeks():
    with pytest.raises(ValueError):
        calculate_greeks(spot=100,strike=100,years=0,volatility=.2,rate=.05,dividend=0,right=Right.CALL)

def test_purged_training_and_validation():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=tuple(Sample(t+timedelta(minutes=i),t+timedelta(minutes=i+2),
                      (float(i%2),),100. if i%2 else -50.,"momentum") for i in range(300))
    cutoff=t+timedelta(minutes=200)
    m=fit(rows,cutoff=cutoff)
    assert m==fit(rows[:198],cutoff=cutoff)
    assert m.probability((1.,))>m.probability((0.,))
    holdout=rows[200:]
    v=validate(m,holdout)
    assert v.brier<v.baseline_brier
    assert v.net_pnl>0
    assert select_signal({"momentum":m},(1.,),at=t+timedelta(minutes=310),validation={"momentum":v})[1]=="momentum"
    assert select_signal({"momentum":m},(0.,),at=t+timedelta(minutes=310),validation={"momentum":v}) is None
    with pytest.raises(ValueError,match="overlaps"):
        validate(m,rows)
