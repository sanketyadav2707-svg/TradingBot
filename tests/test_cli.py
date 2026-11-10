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
