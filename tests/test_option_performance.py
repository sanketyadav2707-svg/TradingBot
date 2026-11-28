from decimal import Decimal as D

import pytest

from tradingbot.research.option_performance import evaluate_option_performance


def test_win_rate_below_half_can_be_profitable():
    report = evaluate_option_performance((D("-100"), D("-100"), D("-100"), D("500"), D("500")))
    assert report.win_rate == D("0.4")
    assert report.net_pnl == D("700")
    assert report.expectancy_per_trade == D("140")
    assert report.longest_losing_streak == 3
    assert report.estimated_break_even_win_rate == D("0.1666666666666666666666666667")


def test_high_win_rate_can_still_lose_after_costs():
    report = evaluate_option_performance((D("20"), D("20"), D("20"), D("20"), D("-300")))
    assert report.win_rate == D("0.8")
    assert report.net_pnl == D("-220")
    assert report.max_drawdown == D("300")
    assert not report.profitable_after_costs


def test_zero_loss_profit_factor_is_not_fabricated():
    report = evaluate_option_performance((D("10"), D("0")))
    assert report.profit_factor is None
    assert report.breakeven == 1


def test_invalid_pnl_input_rejected():
    with pytest.raises(ValueError):
        evaluate_option_performance(())
    with pytest.raises(ValueError, match="finite"):
        evaluate_option_performance((D("NaN"),))
