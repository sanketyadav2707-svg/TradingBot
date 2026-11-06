import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "integrations" / "quantconnect" / "orb15_trade_sim.py"


def source():
    return SCRIPT.read_text(encoding="utf-8")


def load_function(name):
    tree = ast.parse(source())
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {
        "random": __import__("random"),
        "INITIAL_RESEARCH_EQUITY": 100_000.0,
        "BOOTSTRAP_BLOCK_DAYS": 5,
        "BOOTSTRAP_REPLICATES": 1000,
        "BOOTSTRAP_SEED": 20261105,
        "ROUND_TURN_COMMISSION_USD": 1.14,
    }
    if name == "calculate_scenario_metrics":
        helper_node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "block_bootstrap_mean_ci"
        )
        helper_module = ast.Module(body=[helper_node], type_ignores=[])
        exec(compile(helper_module, str(SCRIPT), "exec"), namespace)
    exec(compile(module, str(SCRIPT), "exec"), namespace)
    return namespace[name]


def test_script_is_valid_python_syntax():
    compile(source(), str(SCRIPT), "exec")


def test_script_never_places_orders():
    tree = ast.parse(source())
    forbidden = {
        "market_order", "limit_order", "stop_market_order", "set_holdings",
        "liquidate", "buy", "sell", "MarketOrder", "LimitOrder",
    }
    calls = [
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden
    ]
    assert calls == []
    assert '"Orders sent", 0' in source()


def test_orb_requires_one_full_tick_beyond_opening_range():
    fn = load_function("opening_range_direction")
    assert fn(101.00, 101.00, 99.00, 0.25) == 0
    assert fn(101.25, 101.00, 99.00, 0.25) == 1
    assert fn(98.75, 101.00, 99.00, 0.25) == -1


def test_trade_pnl_includes_round_turn_fees_and_two_sided_slippage():
    fn = load_function("calculate_trade_pnl")
    zero = fn(20000, 20001, 1, 2, 0.25, 0)
    one = fn(20000, 20001, 1, 2, 0.25, 1)
    two = fn(20000, 20001, 1, 2, 0.25, 2)
    assert zero["gross_dollars"] == 2.0
    assert abs(zero["net_dollars"] - 0.86) < 1e-9
    assert abs(one["net_dollars"] + 0.14) < 1e-9
    assert abs(two["net_dollars"] + 1.14) < 1e-9


def test_trade_pnl_rejects_invalid_direction_or_nonpositive_price():
    fn = load_function("calculate_trade_pnl")
    try:
        fn(20000, 20001, 0, 2, 0.25, 0)
        assert False, "direction 0 should fail"
    except ValueError:
        pass
    try:
        fn(0, 20001, 1, 2, 0.25, 0)
        assert False, "zero entry should fail"
    except ValueError:
        pass


def test_moving_block_bootstrap_is_reproducible_and_handles_short_series():
    fn = load_function("block_bootstrap_mean_ci")
    values = [1.0, -1.0, 2.0, 0.0, 3.0, -2.0, 1.0, 1.0]
    assert fn(values) == fn(values)
    assert fn([4.0]) == (4.0, 4.0)
    assert fn([]) == (0.0, 0.0)


def test_scenario_metrics_calculate_trade_and_daily_risk_statistics():
    fn = load_function("calculate_scenario_metrics")
    trades = [
        {"net_dollars": {0: 10.0, 1: 9.0, 2: 8.0}},
        {"net_dollars": {0: -5.0, 1: -6.0, 2: -7.0}},
        {"net_dollars": {0: -2.0, 1: -3.0, 2: -4.0}},
        {"net_dollars": {0: 8.0, 1: 7.0, 2: 6.0}},
    ]
    metrics = fn(trades, [10.0, -5.0, -2.0, 8.0, 0.0], 0)
    assert metrics["trade_count"] == 4
    assert metrics["total_net_dollars"] == 11.0
    assert metrics["average_net_dollars"] == 2.75
    assert metrics["win_rate_pct"] == 50.0
    assert metrics["profit_factor"] == 18.0 / 7.0
    assert metrics["worst_trade_dollars"] == -5.0
    assert metrics["worst_day_dollars"] == -5.0
    assert metrics["max_consecutive_losses"] == 2
    assert metrics["max_daily_close_drawdown_dollars"] == 7.0
    assert metrics["block_ci_low"] <= metrics["block_ci_high"]


def test_entry_and_exit_assumptions_are_explicit_and_conservative():
    text = source()
    assert '"signal_time": bar_end' in text
    assert '"entry_time": bar_start' in text
    assert '"entry_price": float(bar.open)' in text
    assert "if bar_end == target_time" in text
    assert "elif bar_end > target_time" in text
    assert "if not contiguous or mapping_changed:" in text
    assert "HORIZON_MINUTES = 15" in text


def test_strategy_is_restricted_to_mnq_and_one_opening_range_trade_per_day():
    text = source()
    assert "MICRO_NASDAQ_100_E_MINI" in text
    assert "orb_traded_day" in text
    assert "LAST_SIGNAL_BAR_START = time(10, 30)" in text
    assert "LATEST_ENTRY_BAR_START = time(14, 15)" in text


def test_virtual_trade_enters_next_open_and_exits_on_exact_15m_close(monkeypatch):
    import datetime as dt
    import importlib.util
    import sys
    import types

    class FakeFuture:
        mapped = "MNQ-CONTRACT"
        symbol = "MNQ-CONTRACT"

        def set_filter(self, *_args):
            return None

    class FakeSeries:
        def __init__(self, *args): self.args = args

    class FakeChart:
        def __init__(self, name): self.name = name
        def add_series(self, series): return None

    class FakeQCAlgorithm:
        def __init__(self):
            self.fake_future = FakeFuture()
            self.runtime = {}
            self.plots = []
            self.time_zone = "America/Chicago"
            self.time = dt.datetime(2026, 1, 5, 8, 30)
            self.utc_time = dt.datetime(2026, 1, 5, 14, 30, tzinfo=dt.timezone.utc)
            exchange = types.SimpleNamespace(
                hours=types.SimpleNamespace(time_zone="America/Chicago")
            )
            self.securities = {"MNQ-CONTRACT": types.SimpleNamespace(exchange=exchange)}

        def set_time_zone(self, *_args): pass
        def get_parameter(self, _name): return None
        def set_start_date(self, *_args): pass
        def set_end_date(self, *_args): pass
        def set_cash(self, *_args): pass
        def add_future(self, *_args, **_kwargs): return self.fake_future
        def set_runtime_statistic(self, name, value): self.runtime[name] = value
        def add_chart(self, chart): return None
        def plot(self, *args): self.plots.append(args)

    fake = types.ModuleType("AlgorithmImports")
    fake.QCAlgorithm = FakeQCAlgorithm
    fake.Slice = object
    fake.TimeZones = types.SimpleNamespace(CHICAGO="Chicago")
    fake.Resolution = types.SimpleNamespace(MINUTE="Minute")
    fake.Futures = types.SimpleNamespace(
        Indices=types.SimpleNamespace(MICRO_NASDAQ_100_E_MINI="MNQ")
    )
    fake.DataMappingMode = types.SimpleNamespace(OPEN_INTEREST="OpenInterest")
    fake.DataNormalizationMode = types.SimpleNamespace(RAW="Raw")
    fake.Chart = FakeChart
    fake.Series = FakeSeries
    fake.SeriesType = types.SimpleNamespace(LINE="Line")
    monkeypatch.setitem(sys.modules, "AlgorithmImports", fake)

    spec = importlib.util.spec_from_file_location("orb15_event_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    algorithm = module.MNQORB15EventDrivenBaseline()
    algorithm.initialize()

    class Bar:
        def __init__(self, start, open_, high, low, close):
            self.end_time = start + dt.timedelta(minutes=1)
            self.open = open_
            self.high = high
            self.low = low
            self.close = close

    class SliceStub:
        def __init__(self, bar):
            self.bars = {"MNQ-CONTRACT": bar}

    start = dt.datetime(2026, 1, 5, 8, 30)
    for minute in range(15):
        bar_start = start + dt.timedelta(minutes=minute)
        algorithm.time = bar_start + dt.timedelta(minutes=1)
        algorithm.utc_time = (algorithm.time + dt.timedelta(hours=6)).replace(tzinfo=dt.timezone.utc)
        algorithm.on_data(SliceStub(Bar(bar_start, 99.5, 100.0, 99.0, 99.5)))

    signal_start = start + dt.timedelta(minutes=15)
    algorithm.time = signal_start + dt.timedelta(minutes=1)
    algorithm.utc_time = (algorithm.time + dt.timedelta(hours=6)).replace(tzinfo=dt.timezone.utc)
    algorithm.on_data(SliceStub(Bar(signal_start, 100.0, 100.5, 99.75, 100.25)))
    assert algorithm._state["signals"] == 1
    assert algorithm._state["entries"] == 0

    entry_start = start + dt.timedelta(minutes=16)
    for minute in range(15):
        bar_start = entry_start + dt.timedelta(minutes=minute)
        close = 101.0 if minute == 14 else 100.75
        algorithm.time = bar_start + dt.timedelta(minutes=1)
        algorithm.utc_time = (algorithm.time + dt.timedelta(hours=6)).replace(tzinfo=dt.timezone.utc)
        algorithm.on_data(
            SliceStub(Bar(bar_start, 100.5, 101.25, 100.25, close))
        )

    state = algorithm._state
    assert state["entries"] == 1
    assert len(state["trades"]) == 1
    trade = state["trades"][0]
    assert trade["entry_time"] == entry_start
    assert trade["exit_time"] == entry_start + dt.timedelta(minutes=15)
    assert trade["direction"] == 1
    assert trade["gross_dollars"] == 1.0
    assert abs(trade["net_dollars"][0] + 0.14) < 1e-9
    assert trade["mfe_points"] == 0.75
    assert trade["mae_points"] == 0.25
    assert state["invalidated"] == 0
    assert all("order" not in str(call).lower() for call in algorithm.plots)

    assert "First RTH time audit" not in algorithm.runtime
    algorithm.on_end_of_algorithm()
    assert "Algorithm time zone" in algorithm.runtime
    assert algorithm.runtime["MNQ exchange time zone"] == "America/Chicago"
    assert "First RTH time audit" in algorithm.runtime
    assert "First 3 trade times" in algorithm.runtime
    assert "sigEnd=01-05 08:46" in algorithm.runtime["First 3 trade times"]
    assert "entry=08:46" in algorithm.runtime["First 3 trade times"]
    assert "exit=09:01" in algorithm.runtime["First 3 trade times"]

def test_runtime_statistic_currency_values_are_interpolated():
    text = source()
    assert "$" + "{{" not in text
    assert "total=$" + "{metrics[" in text
    assert "mean=$" + "{metrics[" in text

def test_daily_metrics_only_include_rth_session_dates():
    text = source()
    assert "if time(8, 30) <= bar_start.time() < time(15, 0):" in text

def test_time_audit_uses_algorithm_and_exchange_time_zones():
    text = source()
    assert 'self.set_runtime_statistic("Algorithm time zone", str(self.time_zone))' in text
    assert 'self.securities[self._future.symbol].exchange.hours.time_zone' in text
    assert 'self.utc_time.strftime' in text
    assert 'bar.time.strftime' in text
    assert 'bar.end_time.strftime' in text


def test_excursion_chart_labels_values_as_index_points_not_dollars():
    text = source()
    assert 'Series("MFE points", SeriesType.LINE, "MNQ index points")' in text
    assert 'Series("MAE points", SeriesType.LINE, "MNQ index points")' in text
