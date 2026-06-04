"""Tests for OpenBB market data adapter (mocked; no live internet)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.external import openbb_client as oc
from src.external.openbb_client import (
    OPENBB_IMPORT_ERROR,
    PRICE_HISTORY_COLUMNS,
    fetch_openbb_price_history,
    fetch_openbb_quote,
    validate_price_history_output,
)
from src.portfolio.metrics_builder import REQUIRED_PRICE_TICKERS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCRIPT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "openbb_price_history.csv"


class _FakeObbResult:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def to_df(self) -> pd.DataFrame:
        return self._frame


def _fake_obb_with_history(frame: pd.DataFrame) -> MagicMock:
    obb = MagicMock()
    obb.equity.price.historical.return_value = _FakeObbResult(frame)
    obb.equity.price.quote.side_effect = AttributeError("no quote in test")
    return obb


def test_import_error_when_openbb_missing():
    with patch.dict(sys.modules, {"openbb": None}):
        with patch(
            "src.external.openbb_client._import_openbb",
            side_effect=ImportError(OPENBB_IMPORT_ERROR),
        ):
            with pytest.raises(ImportError, match="pip install openbb"):
                fetch_openbb_quote("SPY")


def test_quote_normalization_from_history_fallback():
    hist = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-04-01", "2026-04-02"]),
            "close": [500.0, 505.5],
        }
    )
    with patch("src.external.openbb_client._import_openbb", return_value=_fake_obb_with_history(hist)):
        quote = fetch_openbb_quote("SPY", provider="yfinance")
    assert quote["symbol"] == "SPY"
    assert quote["close"] == pytest.approx(505.5)
    assert quote["source"] == "openbb_yfinance"
    assert quote["provider"] == "yfinance"


def test_price_history_normalization_long_format():
    hist = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-04-01", "2026-04-02"]),
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.05, 2.05],
            "volume": [100, 200],
        }
    )

    def _obb_side_effect(*_args, **kwargs):
        symbol = kwargs.get("symbol")
        if symbol == "^VIX":
            vix = hist.copy()
            vix["close"] = [15.0, 16.0]
            return _FakeObbResult(vix)
        return _FakeObbResult(hist)

    obb = MagicMock()
    obb.equity.price.historical.side_effect = _obb_side_effect

    with patch("src.external.openbb_client._import_openbb", return_value=obb):
        df = fetch_openbb_price_history(
            ["SPY", "VIX"],
            start_date="2026-04-01",
            end_date="2026-04-02",
            provider="yfinance",
        )

    assert list(df.columns) == PRICE_HISTORY_COLUMNS
    assert set(df["ticker"].unique()) == {"SPY", "VIX"}
    assert (df["source"] == "openbb_yfinance").all()
    assert df["close"].notna().all()


def test_price_history_normalization_accepts_named_date_index():
    hist = pd.DataFrame(
        {
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.05, 2.05],
            "volume": [100, 200],
        },
        index=pd.Index(
            [pd.Timestamp("2026-04-01").date(), pd.Timestamp("2026-04-02").date()],
            name="date",
        ),
    )

    with patch("src.external.openbb_client._import_openbb", return_value=_fake_obb_with_history(hist)):
        df = fetch_openbb_price_history(
            ["SPY"],
            start_date="2026-04-01",
            end_date="2026-04-02",
            provider="yfinance",
        )

    assert list(df.columns) == PRICE_HISTORY_COLUMNS
    assert df["ticker"].tolist() == ["SPY", "SPY"]
    assert df["close"].tolist() == [1.05, 2.05]


def test_duplicate_ticker_date_raises():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-04-01", "2026-04-01"]),
            "ticker": ["SPY", "SPY"],
            "close": [1.0, 1.1],
            "source": ["openbb_yfinance", "openbb_yfinance"],
        }
    )
    with pytest.raises(ValueError, match="duplicate ticker/date"):
        validate_price_history_output(df)


def test_missing_close_raises():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-04-01"]),
            "ticker": ["SPY"],
            "close": [None],
            "source": ["openbb_yfinance"],
        }
    )
    with pytest.raises(ValueError, match="missing close"):
        validate_price_history_output(df)


def test_vix_maps_to_caret_vix_for_yfinance():
    captured: list[str] = []

    def _capture(symbol, **kwargs):
        captured.append(str(symbol))
        return _FakeObbResult(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-04-01"]),
                    "close": [20.0],
                }
            )
        )

    obb = MagicMock()
    obb.equity.price.historical.side_effect = _capture

    with patch("src.external.openbb_client._import_openbb", return_value=obb):
        fetch_openbb_price_history(
            ["VIX"],
            start_date="2026-04-01",
            end_date="2026-04-01",
            provider="yfinance",
        )

    assert captured == ["^VIX"]


def test_fetch_script_default_output_is_data_raw():
    from scripts import fetch_openbb_prices as script

    assert script.DEFAULT_OUTPUT == DEFAULT_SCRIPT_OUTPUT
    assert "data/raw" in script.DEFAULT_OUTPUT.as_posix()


def test_fetch_script_default_universe_uses_etf_universe():
    from scripts import fetch_openbb_prices as script

    tickers = script._resolve_tickers("etf_universe")
    assert len(tickers) >= 39
    assert "SPY" in tickers
    assert "VIX" in tickers
    assert "VXX" not in tickers
    assert script._resolve_tickers("required_metrics") == list(REQUIRED_PRICE_TICKERS)
