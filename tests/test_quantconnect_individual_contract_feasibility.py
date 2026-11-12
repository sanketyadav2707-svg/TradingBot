import ast
import json
from pathlib import Path

NOTEBOOK = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "quantconnect"
    / "phase3_individual_contract_feasibility.ipynb"
)


def _source() -> str:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert len(code_cells) == 1
    return "".join(code_cells[0]["source"])


def test_quantconnect_individual_contract_notebook_is_valid_python() -> None:
    compile(_source(), str(NOTEBOOK), "exec")


def test_quantconnect_notebook_requests_individual_contract_minute_history() -> None:
    source = _source()
    assert "qb.history(\\n        FutureUniverse" in source
    assert "qb.history(\n            TradeBar," in source
    assert "Resolution.MINUTE" in source
    assert "Futures.Indices.MicroSP500EMini" in source
    assert "Futures.Indices.MicroNASDAQ100EMini" in source


def test_quantconnect_notebook_displays_aggregate_diagnostics_only() -> None:
    tree = ast.parse(_source())
    forbidden_methods = {
        "to_csv", "to_parquet", "to_pickle", "to_json",
        "savefig", "plot", "log", "debug", "write_text",
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_methods:
                found.append(node.func.attr)
    assert found == []
    displays = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "display"
    ]
    assert len(displays) == 2
    rendered = [ast.unparse(node.args[0]) for node in displays]
    assert rendered[0] == "root_summary"
    assert "contract_summary.groupby" in rendered[1]
    assert "bars" not in rendered[0] or "individual_contract_minute_bars" in rendered[0]


def test_quantconnect_notebook_never_submits_orders() -> None:
    tree = ast.parse(_source())
    forbidden = {
        "market_order", "limit_order", "stop_market_order",
        "set_holdings", "liquidate", "buy", "sell",
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden:
                found.append(node.func.attr)
    assert found == []
