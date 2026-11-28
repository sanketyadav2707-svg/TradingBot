"""Deterministic offline logistic baseline with purged chronological splits."""
from dataclasses import dataclass
from datetime import datetime
from math import exp, isfinite, sqrt, log
from tradingbot.risk.index_options import aware


@dataclass(frozen=True, slots=True)
class Sample:
    at: datetime
    label_end: datetime
    features: tuple[float, ...]
    net_pnl: float
    strategy: str

    def __post_init__(self):
        if aware(self.at,"at") >= aware(self.label_end,"label_end"):
            raise ValueError("invalid_label_interval")
        if not self.features or not all(isfinite(x) for x in self.features):
            raise ValueError("invalid_features")
        if not isfinite(self.net_pnl) or not self.strategy:
            raise ValueError("invalid_outcome")


@dataclass(frozen=True, slots=True)
class Model:
    mean: tuple[float,...]
    scale: tuple[float,...]
    weights: tuple[float,...]
    intercept: float
    trained_until: datetime

    def probability(self, features):
        if len(features)!=len(self.weights) or not all(isfinite(x) for x in features):
            raise ValueError("feature_schema_mismatch")
        z=self.intercept+sum(w*(x-m)/s for w,x,m,s in zip(
            self.weights,features,self.mean,self.scale))
        return sigmoid(z)


def sigmoid(z):
    return 1/(1+exp(-max(-40,min(40,z))))


def fit(samples, *, cutoff, min_samples=100, steps=400, learning_rate=.05, l2=.01):
    cutoff=aware(cutoff,"cutoff")
    if type(min_samples) is not int or min_samples<2 or type(steps) is not int or steps<1:
        raise ValueError("invalid_training_configuration")
    if not isfinite(learning_rate) or not 0<learning_rate<=1 or not isfinite(l2) or l2<0:
        raise ValueError("invalid_optimizer")
    rows=[s for s in samples if aware(s.label_end,"end")<cutoff]
    if len(rows)<min_samples or len({s.net_pnl>0 for s in rows})<2:
        raise ValueError("insufficient_training_evidence")
    n=len(rows); k=len(rows[0].features)
    if any(len(s.features)!=k for s in rows):
        raise ValueError("feature_schema_mismatch")
    mean=tuple(sum(s.features[j] for s in rows)/n for j in range(k))
    scale=tuple(max(1e-9,sqrt(sum((s.features[j]-mean[j])**2 for s in rows)/n)) for j in range(k))
    xs=[tuple((x-m)/v for x,m,v in zip(s.features,mean,scale)) for s in rows]
    ys=[float(s.net_pnl>0) for s in rows]
    w=[0.]*k; b=0.
    for _ in range(steps):
        err=[sigmoid(b+sum(a*x for a,x in zip(w,row)))-y for row,y in zip(xs,ys)]
        w=[a-learning_rate*(sum(e*x[j] for e,x in zip(err,xs))/n+l2*a) for j,a in enumerate(w)]
        b-=learning_rate*sum(err)/n
    return Model(mean,scale,tuple(w),b,cutoff)


@dataclass(frozen=True, slots=True)
class Validation:
    samples: int
    brier: float
    log_loss: float
    baseline_brier: float
    accepted: int
    net_pnl: float


def validate(model, samples, *, threshold=.7, baseline_probability=.5):
    if not 0<threshold<1 or not 0<baseline_probability<1:
        raise ValueError("invalid_probability_threshold")
    rows=tuple(samples)
    if not rows or any(aware(s.at,"at")<model.trained_until for s in rows):
        raise ValueError("holdout_overlaps_training")
    p=[model.probability(s.features) for s in rows]
    y=[float(s.net_pnl>0) for s in rows]
    n=len(rows)
    return Validation(n,sum((a-b)**2 for a,b in zip(p,y))/n,
        -sum(b*log(max(a,1e-15))+(1-b)*log(max(1-a,1e-15)) for a,b in zip(p,y))/n,
        sum((baseline_probability-b)**2 for b in y)/n,
        sum(a>=threshold for a in p),
        sum(s.net_pnl for a,s in zip(p,rows) if a>=threshold))


def select_signal(models, features, *, at, validation, min_validation=50,
                  threshold=.7):
    """Rank only independently validated candidates; return None to abstain.
    Validation reports must come from a frozen earlier window. This is research
    scoring, not a risk gate or live order authorization.
    """
    now=aware(at,"decision")
    candidates=[]
    for name,model in models.items():
        report=validation.get(name)
        if (model.trained_until>now or report is None or report.samples<min_validation
                or report.accepted==0 or report.net_pnl<=0
                or report.brier>=report.baseline_brier):
            continue
        p=model.probability(features)
        if p>=threshold:
            candidates.append((p,name))
    return max(candidates) if candidates else None
