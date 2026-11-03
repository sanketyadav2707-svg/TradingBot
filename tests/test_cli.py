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
