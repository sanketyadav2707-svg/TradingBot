import ast
from pathlib import Path


QC_PROBE = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "quantconnect"
    / "main.py"
)


def _probe_source() -> str:
    return QC_PROBE.read_text(encoding="utf-8")


def test_quantconnect_probe_is_valid_python_syntax() -> None:
    compile(_probe_source(), str(QC_PROBE), "exec")


def test_quantconnect_probe_never_submits_trading_orders() -> None:
    tree = ast.parse(_probe_source())
    forbidden_calls = {
        "market_order",
        "limit_order",
        "stop_market_order",
        "set_holdings",
        "liquidate",
        "buy",
        "sell",
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_calls:
                found.append(node.func.attr)
    assert found == []


def test_quantconnect_probe_reports_aggregate_metrics_not_raw_prices() -> None:
    source = _probe_source()
    tree = ast.parse(source)
    assert "HORIZONS_MINUTES = (3, 5, 10, 15)" in source
    assert "avg abs move bps" in source
    assert "move stdev bps" in source
    assert "positive pct" in source
    assert "self.log(" not in source
    assert "self.plot(" not in source

    # Market prices may be read for calculations, but must not be passed
    # directly into runtime-statistic or logging/plotting calls.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"set_runtime_statistic", "log", "plot", "debug"}:
            rendered = ast.unparse(node)
            assert "bar.close" not in rendered


def test_quantconnect_probe_skips_nonmatching_horizon_timestamps() -> None:
    source = _probe_source()
    assert "close_history.get(previous_time)" in source
    assert "current_time - timedelta(minutes=horizon)" in source
