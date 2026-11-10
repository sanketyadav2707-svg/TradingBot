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
    assert "abs={average_abs_bps:.3f}bps" in source
    assert "sd={stddev_bps:.3f}bps" in source
    assert "up={positive_pct:.2f}%" in source
    assert "pairs=" in source
    assert "contUp=" in source
    assert "contDn=" in source
    assert "elapsed_seconds < target_seconds" in source
    assert "elapsed_seconds > target_seconds" in source
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


def _load_window_helper():
    import ast
    from datetime import datetime

    tree = ast.parse(_probe_source())
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_update_nonoverlap"
    )
    module = ast.Module(body=[helper], type_ignores=[])
    namespace = {"datetime": datetime}
    exec(compile(module, str(QC_PROBE), "exec"), namespace)
    return namespace["_update_nonoverlap"]


def _window_state() -> dict:
    return {
        "anchor_time": None,
        "anchor_close": None,
        "previous_return_bps": None,
        "session_bucket": None,
        "pairs": 0,
        "after_up": 0,
        "after_up_continued": 0,
        "after_down": 0,
        "after_down_continued": 0,
    }


def test_nonoverlap_helper_counts_consecutive_up_windows() -> None:
    from datetime import datetime, timedelta

    update = _load_window_helper()
    state = _window_state()
    start = datetime(2026, 1, 5, 9, 30)

    update(state, 3, start, 100.0, False, "RTH_OPEN")
    for minute in range(1, 7):
        # Two non-overlapping 3-minute price rises.
        close = 100.0 + minute * 0.1
        update(state, 3, start + timedelta(minutes=minute), close, True, "RTH_OPEN")

    assert state["pairs"] == 1
    assert state["after_up"] == 1
    assert state["after_up_continued"] == 1


def test_nonoverlap_helper_resets_after_gap() -> None:
    from datetime import datetime, timedelta

    update = _load_window_helper()
    state = _window_state()
    start = datetime(2026, 1, 5, 9, 30)

    update(state, 3, start, 100.0, False, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=1), 100.1, True, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=2), 100.2, True, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=3), 100.3, True, "RTH_OPEN")
    assert state["previous_return_bps"] is not None

    # A gap invalidates the prior sequence, so a pair cannot bridge it.
    update(state, 3, start + timedelta(minutes=5), 100.4, False, "RTH_OPEN")
    assert state["previous_return_bps"] is None
    update(state, 3, start + timedelta(minutes=6), 100.5, True, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=7), 100.6, True, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=8), 100.7, True, "RTH_OPEN")

    assert state["pairs"] == 0


def test_probe_updates_nonoverlap_state_for_each_horizon() -> None:
    tree = ast.parse(_probe_source())
    algorithm = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "FuturesDataCoverageProbe"
    )
    on_data = next(
        node for node in algorithm.body
        if isinstance(node, ast.FunctionDef) and node.name == "on_data"
    )
    horizon_loops = [
        node for node in ast.walk(on_data)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "horizon"
        and isinstance(node.iter, ast.Attribute)
        and node.iter.attr == "HORIZONS_MINUTES"
    ]
    assert any(
        any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_update_nonoverlap"
            for statement in loop.body
            for node in ast.walk(statement)
        )
        for loop in horizon_loops
    )


def test_probe_compacts_runtime_statistics_and_resets_gaps() -> None:
    source = _probe_source()
    assert 'f"V2 {root} {horizon}m profile"' in source
    assert 'f"SESSION {root} {bucket} {horizon}m"' in source
    assert "self.set_time_zone(TimeZones.CHICAGO)" in source
    assert 'if not is_contiguous:' in source
    assert "close_history.clear()" in source


def _load_session_bucket_helper():
    from datetime import datetime, time

    tree = ast.parse(_probe_source())
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_session_bucket"
    )
    module = ast.Module(body=[helper], type_ignores=[])
    namespace = {"datetime": datetime, "time": time}
    exec(compile(module, str(QC_PROBE), "exec"), namespace)
    return namespace["_session_bucket"]


def test_session_bucket_uses_cme_chicago_windows() -> None:
    from datetime import datetime

    classify = _load_session_bucket_helper()
    assert classify(datetime(2026, 1, 5, 8, 30)) == "RTH_OPEN"
    assert classify(datetime(2026, 1, 5, 8, 59)) == "RTH_OPEN"
    assert classify(datetime(2026, 1, 5, 9, 0)) == "RTH_CORE"
    assert classify(datetime(2026, 1, 5, 14, 29)) == "RTH_CORE"
    assert classify(datetime(2026, 1, 5, 14, 30)) == "RTH_CLOSE"
    assert classify(datetime(2026, 1, 5, 14, 59)) == "RTH_CLOSE"
    assert classify(datetime(2026, 1, 5, 15, 0)) == "FUTURES_LATE_RTH"
    assert classify(datetime(2026, 1, 5, 15, 59)) == "FUTURES_LATE_RTH"
    assert classify(datetime(2026, 1, 5, 16, 0)) == "GLOBEX_OTHER"


def test_nonoverlap_helper_resets_when_session_bucket_changes() -> None:
    from datetime import datetime, timedelta

    update = _load_window_helper()
    state = _window_state()
    start = datetime(2026, 1, 5, 8, 57)

    update(state, 3, start, 100.0, False, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=1), 100.1, True, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=2), 100.2, True, "RTH_OPEN")
    update(state, 3, start + timedelta(minutes=3), 100.3, True, "RTH_CORE")

    assert state["previous_return_bps"] is None
    assert state["session_bucket"] == "RTH_CORE"
    assert state["pairs"] == 0



def test_session_bucket_uses_bar_interval_start_not_end_time() -> None:
    from datetime import datetime, timedelta

    classify = _load_session_bucket_helper()
    # A bar ending at 09:00 CT covers 08:59-09:00 and belongs to RTH_OPEN.
    end_time = datetime(2026, 1, 5, 9, 0)
    assert classify(end_time - timedelta(minutes=1)) == "RTH_OPEN"
    # A bar ending at 09:01 CT covers 09:00-09:01 and belongs to RTH_CORE.
    end_time = datetime(2026, 1, 5, 9, 1)
    assert classify(end_time - timedelta(minutes=1)) == "RTH_CORE"
    # Similarly, 14:30 is the start of the cash-close bucket, not its previous minute.
    end_time = datetime(2026, 1, 5, 14, 31)
    assert classify(end_time - timedelta(minutes=1)) == "RTH_CLOSE"


def test_probe_classifies_bar_by_interval_start() -> None:
    source = _probe_source()
    assert "bar_start_time = current_time - timedelta(minutes=1)" in source
    assert "_session_bucket(bar_start_time)" in source


def test_probe_uses_explicit_roll_events_and_mapped_raw_contract_bars() -> None:
    source = _probe_source()
    assert "slice.symbol_changed_events.get(future.symbol)" in source
    assert "changed_event.old_symbol" in source
    assert "changed_event.new_symbol" in source
    assert "stats[\"roll_reset_pending\"] = True" in source
    assert "bar = slice.bars.get(mapped_symbol)" in source
    assert "slice.bars.get(future.symbol)" not in source
    assert 'f"{root} roll audit"' in source


def test_probe_roll_event_without_immediate_bar_keeps_reset_pending() -> None:
    source = _probe_source()
    assert source.index('stats["roll_reset_pending"] = True') < source.index(
        'bar = slice.bars.get(mapped_symbol)'
    )
    assert source.index('if bar is None:') < source.index(
        'stats["roll_reset_pending"] = False'
    )
    assert "unannounced_mapping_changes" in source
    assert "roll_event_mismatches" in source
