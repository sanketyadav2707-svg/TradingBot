"""European index-option Black-Scholes-Merton research sensitivities.

Rates, dividend yield and annualized IV are explicit scenario inputs.
Theta is per calendar day, vega per one percentage point of volatility.
Model prices are not executable quotes.
"""
from dataclasses import dataclass
from math import erf, exp, isfinite, log, pi, sqrt
from tradingbot.risk.index_options import Right


@dataclass(frozen=True, slots=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_point: float


def calculate_greeks(*, spot: float, strike: float, years: float,
                     volatility: float, rate: float, dividend: float,
                     right: Right) -> Greeks:
    values = (spot, strike, years, volatility, rate, dividend)
    if any(isinstance(x, bool) or not isfinite(x) for x in values):
        raise ValueError("nonfinite_pricing_inputs")
    if min(spot, strike, years, volatility) <= 0 or not isinstance(right, Right):
        raise ValueError("invalid_pricing_inputs")
    if years > 10 or volatility > 5 or abs(rate) > 1 or abs(dividend) > 1:
        raise ValueError("pricing_inputs_outside_model_domain")
    n = lambda x: (1 + erf(x / sqrt(2))) / 2
    t = sqrt(years)
    d1 = (log(spot / strike) + (rate-dividend+volatility**2/2)*years)/(volatility*t)
    d2 = d1-volatility*t
    ds, dk = exp(-dividend*years), exp(-rate*years)
    density = exp(-d1*d1/2)/sqrt(2*pi)
    gamma = ds*density/(spot*volatility*t)
    vega = spot*ds*density*t/100
    common = -spot*ds*density*volatility/(2*t)
    if right is Right.CALL:
        price = spot*ds*n(d1)-strike*dk*n(d2)
        delta = ds*n(d1)
        theta = common-rate*strike*dk*n(d2)+dividend*spot*ds*n(d1)
    else:
        price = strike*dk*n(-d2)-spot*ds*n(-d1)
        delta = -ds*n(-d1)
        theta = common+rate*strike*dk*n(-d2)-dividend*spot*ds*n(-d1)
    return Greeks(max(0.,price),delta,gamma,theta/365,vega)


def reprice_shock(*, spot: float, strike: float, years: float,
                  volatility: float, rate: float, dividend: float, right: Right,
                  spot_return: float, iv_change: float, elapsed_seconds: int) -> float:
    """Reprice a hypothetical scenario, not a predicted future premium."""
    if type(elapsed_seconds) is not int or elapsed_seconds < 0:
        raise ValueError("invalid_elapsed_seconds")
    calculate_greeks(spot=spot,strike=strike,years=years,volatility=volatility,
                     rate=rate,dividend=dividend,right=right)
    if not isfinite(spot_return) or not isfinite(iv_change) or spot_return <= -1:
        raise ValueError("invalid_shock")
    remaining = years-elapsed_seconds/(365*86400)
    shocked = spot*(1+spot_return)
    if remaining <= 0:
        return max(0.,shocked-strike if right is Right.CALL else strike-shocked)
    return calculate_greeks(spot=shocked,strike=strike,years=remaining,
                            volatility=volatility+iv_change,rate=rate,
                            dividend=dividend,right=right).price
