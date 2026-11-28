"""Expanding-window, purged evaluation of frozen logistic model ensembles.

Research only. Evaluation samples are not necessarily independent portfolio trades.
"""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from tradingbot.risk.index_options import aware
from tradingbot.research.option_ml import Sample, Model, fit, validate, Validation


@dataclass(frozen=True, slots=True)
class Ensemble:
    models: tuple[Model, ...]
    trained_until: datetime

    def probability(self, features):
        return sum(m.probability(features) for m in self.models)/len(self.models)


@dataclass(frozen=True, slots=True)
class Fold:
    strategy: str
    start: datetime
    end: datetime
    report: Validation
    threshold: float


def walk_forward(samples: tuple[Sample,...], *, boundaries: tuple[datetime,...],
                 strategy: str, threshold: float=.7, min_train: int=100,
                 min_test: int=30, penalties: tuple[float,...]=(.001,.01,.1)) -> tuple[Fold,...]:
    """Train only on completed earlier labels; test on disjoint later intervals.

    All hyperparameters and boundaries must be fixed before evaluation.
    No threshold tuning or model selection on these test folds.
    """
    cuts=tuple(aware(x,"boundary") for x in boundaries)
    if len(cuts)<2 or any(a>=b for a,b in zip(cuts,cuts[1:])):
        raise ValueError("invalid_fold_boundaries")
    if not 0<threshold<1 or type(min_train) is not int or min_train<2 or type(min_test) is not int or min_test<1:
        raise ValueError("invalid_evaluation_settings")
    if not penalties or any(not isfinite(x) or x<0 for x in penalties):
        raise ValueError("invalid_penalties")
    rows=sorted((s for s in samples if s.strategy==strategy),key=lambda s: aware(s.at,"at"))
    if any(aware(a.label_end,"end")>=aware(b.at,"at") for a,b in zip(rows,rows[1:])):
        raise ValueError("overlapping_strategy_labels")
    result=[]
    for start,end in zip(cuts,cuts[1:]):
        train=tuple(s for s in rows if aware(s.label_end,"end")<start)
        test=tuple(s for s in rows if start<=aware(s.at,"at") and aware(s.label_end,"end")<end)
        if len(train)<min_train or len(test)<min_test:
            raise ValueError("insufficient_fold_samples")
        base=sum(s.net_pnl>0 for s in train)/len(train)
        if not 0<base<1:
            raise ValueError("single_class_training_fold")
        models=tuple(fit(train,cutoff=start,min_samples=min_train,l2=p) for p in penalties)
        ensemble=Ensemble(models,start)
        report=validate(ensemble,test,threshold=threshold,baseline_probability=base)
        result.append(Fold(strategy,start,end,report,threshold))
    return tuple(result)
