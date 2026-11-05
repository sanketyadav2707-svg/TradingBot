import ast
from pathlib import Path


LAB = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "quantconnect"
    / "strategy_lab.py"
)


def _source() -> str:
    return LAB.read_text(encoding="utf-8")


def _load_function(name: str):
    tree = ast.parse(_source())
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {
        "time": __import__("datetime").time,
        "ROUND_TURN_COMMISSION_USD": 1.14,
    }
    exec(compile(module, str(LAB), "exec"), namespace)
    return namespace[name]


def test_strategy_lab_is_valid_python_syntax() -> None:
    compile(_source(), str(LAB), "exec")


def test_strategy_lab_never_places_orders() -> None:
    tree = ast.parse(_source())
    forbidden = {
        "market_order", "limit_order", "stop_market_order", "set_holdings",
        "liquidate", "buy", "sell", "MarketOrder", "LimitOrder",
    }
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden
    ]
    assert calls == []
    assert '"Orders sent", 0' in _source()


def test_opening_range_breakout_requires_one_tick_clearance() -> None:
    fn = _load_function("opening_range_direction")
    assert fn(101.25, 101.0, 99.0, 0.25) == 0
    assert fn(101.26, 101.0, 99.0, 0.25) == 1
    assert fn(98.74, 101.0, 99.0, 0.25) == -1


def test_vwap_pullback_requires_trend_and_reclaim() -> None:
    fn = _load_function("vwap_pullback_direction")
    assert fn(101, 100, 101.5, 100.5, 100.8, 100.2) == 1
    assert fn(100, 100.5, 100.8, 100.5, 100.8, 100.2) == 0
    assert fn(99, 98.5, 100, 99.5, 99.2, 99.8) == -1


def test_compression_breakout_uses_only_previous_bars() -> None:
    fn = _load_function("compression_breakout_direction")
    ranges = [2.0] * 40 + [1.0] * 20
    highs = [100.0] * 60
    lows = [98.0] * 60
    assert fn(100.1, ranges, highs, lows, 0.25) == 0
    assert fn(100.26, ranges, highs, lows, 0.25) == 1
    assert fn(97.74, ranges, highs, lows, 0.25) == -1
    assert fn(100.26, [2.0] * 60, highs, lows, 0.25) == 0


def test_slippage_and_round_turn_commission_are_included() -> None:
    fn = _load_function("net_return_bps")
    gross = fn(6000, 6001, 1, 5, 0.25, 0)
    one_tick = fn(6000, 6001, 1, 5, 0.25, 1)
    two_ticks = fn(6000, 6001, 1, 5, 0.25, 2)
    assert gross > one_tick > two_ticks


def test_signal_lab_uses_next_bar_open_and_exact_horizon_closes() -> None:
    source = _source()
    assert '"signal_time": bar_end' in source
    assert '"entry_time": bar_start' in source
    assert 'bar.open' in source
    assert 'if bar_end == target_time' in source
    assert 'elif bar_end > target_time' in source


def test_candidate_windows_reset_on_gaps_rolls_and_new_dates() -> None:
    source = _source()
    assert "mapping_changed or day_changed or (previous_end is not None and not contiguous)" in source
    assert "gap/roll invalidated" in source


def test_strategy_lab_has_common_candidate_matrix_and_3_cost_scenarios() -> None:
    source = _source()
    assert 'CANDIDATES = ("ORB15", "VWAP_PULLBACK", "COMPRESSION_BREAKOUT")' in source
    assert "HORIZONS = (3, 5, 10, 15)" in source
    assert "SLIPPAGE_SCENARIOS = (0, 1, 2)" in source
    assert 'for name, state in stats["strategies"].items()' in source
