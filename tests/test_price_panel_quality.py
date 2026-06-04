"""Tests for price panel quality governance (no network)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.price_panel_quality import (
    READINESS_INVALID_CLOSE,
    READINESS_INVALID_DUPLICATES,
    READINESS_INVALID_MISSING,
    READINESS_INVALID_SCHEMA,
    READINESS_OFFICIAL_EOD,
    READINESS_RAW_INCOMPLETE,
    classify_panel_readiness,
    summarize_price_panel,
    validate_official_eod_panel,
)
from src.portfolio.metrics_builder import DEFAULT_PRICE_PATH, REQUIRED_PRICE_TICKERS

ROOT = Path(__file__).resolve().parents[1]
TICKERS = REQUIRED_PRICE_TICKERS


def _complete_openbb_df() -> pd.DataFrame:
    df = pd.read_csv(DEFAULT_PRICE_PATH)
    df["source"] = "openbb_yfinance"
    return df


def test_complete_panel_is_official_eod_ready():
    summary = summarize_price_panel(_complete_openbb_df(), TICKERS)
    assert classify_panel_readiness(summary) == READINESS_OFFICIAL_EOD
    validate_official_eod_panel(_complete_openbb_df(), TICKERS, "openbb_yfinance")


def test_vix_only_holiday_date_is_raw_incomplete():
    df = _complete_openbb_df()
    last_date = df["date"].max()
    partial = df[df["date"] == last_date].head(1).copy()
    partial["date"] = "2099-12-31"
    partial["ticker"] = "VIX"
    raw = pd.concat([df, partial], ignore_index=True)
    summary = summarize_price_panel(raw, TICKERS)
    assert classify_panel_readiness(summary) == READINESS_RAW_INCOMPLETE
    assert summary["incomplete_date_count"] >= 1


def test_missing_required_ticker_is_invalid_missing():
    df = _complete_openbb_df()
    df = df[df["ticker"] != "VIX"].copy()
    summary = summarize_price_panel(df, TICKERS)
    assert classify_panel_readiness(summary) == READINESS_INVALID_MISSING
    assert "VIX" in summary["missing_required_tickers"]


def test_duplicate_date_ticker_is_invalid_duplicates():
    df = _complete_openbb_df()
    dup = df[df["date"] == df["date"].iloc[0]].head(1).copy()
    raw = pd.concat([df, dup], ignore_index=True)
    summary = summarize_price_panel(raw, TICKERS)
    assert classify_panel_readiness(summary) == READINESS_INVALID_DUPLICATES
    assert summary["duplicate_date_ticker_count"] >= 1


def test_official_validator_rejects_incomplete_panel():
    df = _complete_openbb_df()
    dates = sorted(df["date"].unique())
    first_day = df[df["date"] == dates[0]]
    second_day = df[df["date"] == dates[1]]
    second_day = second_day[second_day["ticker"] != "SPY"]
    incomplete = pd.concat([first_day, second_day], ignore_index=True)
    with pytest.raises(ValueError, match="incomplete"):
        validate_official_eod_panel(incomplete, TICKERS, "openbb_yfinance")


def test_official_validator_rejects_wrong_source():
    with pytest.raises(ValueError, match="source"):
        validate_official_eod_panel(
            _complete_openbb_df(),
            TICKERS,
            "sample_synthetic",
        )


def test_official_validator_rejects_null_close():
    df = _complete_openbb_df()
    df.loc[df.index[0], "close"] = None
    with pytest.raises(ValueError, match="null close"):
        validate_official_eod_panel(df, TICKERS, "openbb_yfinance")


def test_non_numeric_close_is_invalid_close():
    df = _complete_openbb_df()
    df["close"] = df["close"].astype(object)
    df.loc[df.index[0], "close"] = "bad"
    summary = summarize_price_panel(df, TICKERS)
    assert classify_panel_readiness(summary) == READINESS_INVALID_CLOSE
    assert summary["close_non_numeric_count"] == 1
    with pytest.raises(ValueError, match="non-numeric close"):
        validate_official_eod_panel(df, TICKERS, "openbb_yfinance")


def test_wrong_schema_summary_is_invalid_schema():
    df = _complete_openbb_df().drop(columns=["source"])
    summary = summarize_price_panel(df, TICKERS)
    assert classify_panel_readiness(summary) == READINESS_INVALID_SCHEMA
    assert summary["schema_valid"] is False
    assert "source" not in df.columns


def test_check_script_writes_json_report(tmp_path):
    from scripts.check_openbb_data_quality import main

    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "aligned.csv"
    report_path = tmp_path / "report.json"
    aligned = _complete_openbb_df()
    aligned.to_csv(proc_path, index=False)
    partial = aligned[aligned["date"] == aligned["date"].iloc[-1]].head(1).copy()
    partial["date"] = "2099-12-31"
    partial["ticker"] = "VIX"
    raw = pd.concat([aligned, partial], ignore_index=True)
    raw.to_csv(raw_path, index=False)

    report = main(
        raw_path=raw_path,
        processed_path=proc_path,
        report_path=report_path,
    )
    assert report_path.exists()
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["raw"]["readiness"] == READINESS_RAW_INCOMPLETE
    assert loaded["processed"]["readiness"] == READINESS_OFFICIAL_EOD
    assert loaded["official_eod_usable"] is True
    assert report["official_eod_usable"] is True
