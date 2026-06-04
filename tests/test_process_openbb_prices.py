"""Tests for OpenBB price alignment script (no network, no OpenBB install)."""

from pathlib import Path

import pandas as pd
import pytest

from src.portfolio.metrics_builder import (
    DEFAULT_PRICE_PATH,
    REQUIRED_PRICE_TICKERS,
    build_metrics_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]


def _openbb_sample_df() -> pd.DataFrame:
    df = pd.read_csv(DEFAULT_PRICE_PATH)
    df["source"] = "openbb_yfinance"
    return df


def test_default_output_path():
    from scripts import process_openbb_prices as script

    assert script.DEFAULT_OUTPUT_PATH == (
        ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
    )
    assert "data/processed" in script.DEFAULT_OUTPUT_PATH.as_posix()


def test_complete_panel_passes():
    from scripts.process_openbb_prices import align_openbb_price_history

    df = _openbb_sample_df()
    aligned, stats = align_openbb_price_history(df)
    assert stats["processed_date_count"] == stats["raw_date_count"]
    assert stats["dropped_incomplete_date_count"] == 0
    assert len(aligned) == len(df)
    assert (aligned["source"] == "openbb_yfinance").all()


def test_incomplete_date_is_dropped(tmp_path):
    from scripts.process_openbb_prices import align_openbb_price_history

    df = _openbb_sample_df()
    last_date = df["date"].max()
    partial = df[df["date"] == last_date].head(1).copy()
    partial["date"] = "2099-12-31"
    raw = pd.concat([df, partial], ignore_index=True)

    aligned, stats = align_openbb_price_history(raw)
    assert stats["dropped_incomplete_date_count"] >= 1
    assert "2099-12-31" not in set(aligned["date"])
    assert stats["processed_date_count"] == stats["raw_date_count"] - 1


def test_missing_required_ticker_fails():
    from scripts.process_openbb_prices import align_openbb_price_history

    df = _openbb_sample_df()
    df = df[df["ticker"] == "SPY"].copy()
    with pytest.raises(ValueError, match="missing entirely"):
        align_openbb_price_history(df)


def test_no_forward_fill():
    from scripts.process_openbb_prices import align_openbb_price_history

    df = _openbb_sample_df()
    dates = sorted(df["date"].unique())
    incomplete = dates[-1]
    raw = df[df["date"] != incomplete].copy()
    partial = df[(df["date"] == incomplete) & (df["ticker"] == "VIX")].copy()
    raw = pd.concat([raw, partial], ignore_index=True)

    aligned, _ = align_openbb_price_history(raw)
    assert incomplete not in set(aligned["date"])
    keep_date = dates[0]
    orig = raw[(raw["date"] == keep_date) & (raw["ticker"] == "SPY")]["close"].iloc[0]
    out = aligned[(aligned["date"] == keep_date) & (aligned["ticker"] == "SPY")]["close"].iloc[0]
    assert out == orig


def test_no_complete_dates_fails():
    from scripts.process_openbb_prices import align_openbb_price_history

    df = _openbb_sample_df()
    day = df[df["date"] == df["date"].iloc[0]].copy()
    spy_dup = pd.concat([day, day[day["ticker"] == "SPY"]], ignore_index=True)
    with pytest.raises(ValueError, match="no complete trading dates"):
        align_openbb_price_history(spy_dup)


def test_processed_output_feeds_metrics_builder(tmp_path):
    from scripts.process_openbb_prices import align_openbb_price_history

    aligned, _ = align_openbb_price_history(_openbb_sample_df())
    out_path = tmp_path / "aligned.csv"
    aligned.to_csv(out_path, index=False)
    snapshot = build_metrics_snapshot(
        price_path=out_path,
        expected_source="openbb_yfinance",
    )
    assert snapshot["data_source"] == "openbb_yfinance_computed_from_prices"


def test_main_writes_aligned_csv(tmp_path):
    from scripts import process_openbb_prices as script

    in_path = tmp_path / "raw.csv"
    out_path = tmp_path / "aligned.csv"
    _openbb_sample_df().to_csv(in_path, index=False)
    script.main(input_path=in_path, output_path=out_path)
    assert out_path.exists()
    loaded = pd.read_csv(out_path)
    assert len(loaded) == len(_openbb_sample_df())
