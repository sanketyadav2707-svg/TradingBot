import ast
from pathlib import Path


QC_PROBE = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "quantconnect"
    / "main.py"
)


def test_quantconnect_probe_is_valid_python_syntax() -> None:
    source = QC_PROBE.read_text(encoding="utf-8")
    compile(source, str(QC_PROBE), "exec")


def test_quantconnect_probe_never_submits_trading_orders() -> None:
    tree = ast.parse(QC_PROBE.read_text(encoding="utf-8"))
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


def test_quantconnect_probe_reports_only_aggregate_coverage_fields() -> None:
    source = QC_PROBE.read_text(encoding="utf-8")
    assert "self.set_runtime_statistic" in source
    assert "bar.close" not in source
    assert "bar.open" not in source
    assert "bar.high" not in source
    assert "bar.low" not in source
    assert "self.log(" not in source
