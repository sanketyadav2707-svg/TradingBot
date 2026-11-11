import json
import sys

from tradingbot.cli import main


def test_sample_backtest_cli_smoke_test(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tradingbot",
            "backtest",
            "--csv",
            "data/sample/MES_5m_sample.csv",
            "--symbol",
            "MES",
            "--config-dir",
            "config",
        ],
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "MES"
    assert payload["starting_balance_usd"] == 50_000.0
    assert isinstance(payload["trades"], int)


def test_raw_data_validation_cli_writes_manifest(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "MES.csv"
    source.write_text(
        "timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume\n"
        "2026-01-05T14:30:00Z,MES,MESH6,101,100,101,99,100,10\n"
        "2026-01-05T14:31:00Z,MES,MESH6,101,100,102,99,101,12\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "MES.metadata.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tradingbot",
            "validate-raw-data",
            "--csv", str(source),
            "--symbol", "MES",
            "--interval-seconds", "60",
            "--manifest", str(manifest),
            "--provider", "fixture",
            "--dataset", "test",
            "--schema", "ohlcv-1m",
        ],
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "validated_with_diagnostics"
    assert payload["contract_count"] == 1
    assert payload["canonical_data_sha256"]
    assert manifest.exists()


def test_raw_data_cli_includes_calendar_gap_classification(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "MES.csv"
    source.write_text(
        "timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume\n"
        "2026-01-05T14:30:00Z,MES,MESH6,101,100,101,99,100,10\n"
        "2026-01-05T14:33:00Z,MES,MESH6,101,100,102,99,101,12\n",
        encoding="utf-8",
    )
    calendar = tmp_path / "calendar.json"
    calendar.write_text(
        '{"calendar_name":"test","timezone":"America/Chicago",'
        '"coverage_start":"2026-01-01","coverage_end":"2026-12-31",'
        '"session_start":"17:00","session_end":"16:00","trade_weekdays":[0,1,2,3,4],'
        '"exceptions":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tradingbot", "validate-raw-data",
            "--csv", str(source), "--symbol", "MES",
            "--interval-seconds", "60", "--calendar", str(calendar),
        ],
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["calendar"]["timezone"] == "America/Chicago"
    assert payload["calendar_gap_classifications"][0]["classification"] == "MISSING_EXPECTED_BARS"
    assert payload["calendar_gap_classifications"][0]["expected_missing_bars"] == 2


def test_convert_databento_csv_cli_writes_canonical_raw_contract_csv(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "databento.csv"
    source.write_text(
        "timestamp,symbol,open,high,low,close,volume,contract_symbol,instrument_id\\n"
        "2026-03-10T14:30:00Z,MES,100,101,99,100,10,MESH6,101\\n",
        encoding="utf-8",
    )
    output = tmp_path / "canonical.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tradingbot", "convert-databento-csv",
            "--input", str(source), "--output", str(output),
            "--symbol", "MES",
        ],
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "converted"
    assert payload["rows"] == 1
    assert "root_symbol,contract_symbol,instrument_id" in output.read_text(encoding="utf-8")


def test_audit_rolls_cli_loads_source_backed_event_json(tmp_path, monkeypatch, capsys) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume\\n"
        "2026-03-10T14:30:00Z,MES,MESH6,101,100,101,99,100,10\\n"
        "2026-03-10T14:31:00Z,MES,MESM6,102,100,102,99,101,10\\n",
        encoding="utf-8",
    )
    events = tmp_path / "rolls.json"
    events.write_text(
        '{"schema_version":1,"events":[{'
        '"root_symbol":"MES","event_time":"2026-03-10T14:31:00Z",'
        '"old_contract_symbol":"MESH6","old_instrument_id":"101",'
        '"new_contract_symbol":"MESM6","new_instrument_id":"102",'
        '"source_url":"https://example.com/provider-event"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tradingbot", "audit-rolls",
            "--csv", str(raw), "--events", str(events), "--symbol", "MES",
        ],
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "verified_against_supplied_events"
    assert payload["event_count"] == 1


def test_backtest_orb15_raw_cli_generates_manifest_and_trade_report(tmp_path, monkeypatch, capsys) -> None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Chicago")
    start = datetime(2026, 11, 9, 8, 30, tzinfo=tz)
    rows = []
    for minute in range(15):
        stamp = start + timedelta(minutes=minute)
        rows.append((stamp, 100.0, 101.0, 99.0, 100.0))
    rows.append((start + timedelta(minutes=15), 100.0, 101.5, 100.0, 101.25))
    rows.append((start + timedelta(minutes=16), 101.25, 104.0, 100.5, 102.0))
    raw = tmp_path / "MES.csv"
    lines = [
        "timestamp,root_symbol,contract_symbol,instrument_id,open,high,low,close,volume"
    ]
    for stamp, open_, high, low, close in rows:
        lines.append(
            f"{stamp.isoformat()},MES,MESZ26,12345,{open_},{high},{low},{close},100"
        )
    raw.write_text("\\n".join(lines) + "\\n", encoding="utf-8")

    calendar = tmp_path / "calendar.json"
    calendar.write_text(
        '{"calendar_name":"test","timezone":"America/Chicago",'
        '"coverage_start":"2026-01-01","coverage_end":"2026-12-31",'
        '"session_start":"17:00","session_end":"16:00","trade_weekdays":[0,1,2,3,4],'
        '"exceptions":[]}',
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tradingbot", "backtest-orb15-raw",
            "--csv", str(raw), "--symbol", "MES",
            "--calendar", str(calendar),
            "--slippage-ticks-per-side", "0",
            "--config-dir", "config",
            "--output", str(output),
        ],
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["research_mode"] == "OFFLINE_ONLY"
    assert payload["dataset_sha256"]
    assert payload["metrics"]["trades"] == 1
    assert len(payload["trades"]) == 1
    assert output.exists()
