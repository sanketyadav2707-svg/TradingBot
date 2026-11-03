import pytest

from tradingbot.data.databento_history import fetch_databento_ohlcv


def test_databento_adapter_requires_local_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DATABENTO_API_KEY"):
        fetch_databento_ohlcv(
            symbol="MES",
            start="2026-01-05T00:00:00Z",
            end="2026-01-06T00:00:00Z",
            output=tmp_path / "MES.csv",
        )


def test_databento_adapter_rejects_unknown_symbol(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    with pytest.raises(ValueError, match="Unsupported micro futures root"):
        fetch_databento_ohlcv(
            symbol="ES",
            start="2026-01-05T00:00:00Z",
            end="2026-01-06T00:00:00Z",
            output=tmp_path / "ES.csv",
        )


def test_databento_adapter_requires_aware_ordered_timestamps(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    with pytest.raises(ValueError, match="timezone"):
        fetch_databento_ohlcv(
            symbol="MES",
            start="2026-01-05T00:00:00",
            end="2026-01-06T00:00:00Z",
            output=tmp_path / "MES.csv",
        )
    with pytest.raises(ValueError, match="earlier"):
        fetch_databento_ohlcv(
            symbol="MES",
            start="2026-01-06T00:00:00Z",
            end="2026-01-05T00:00:00Z",
            output=tmp_path / "MES.csv",
        )
