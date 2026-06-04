"""Tests for read-only live market monitor snapshot (no network)."""

from pathlib import Path

import pandas as pd
import pytest

from src.monitoring.live_market_snapshot import build_market_monitor_snapshot
from src.portfolio.metrics_builder import DEFAULT_PRICE_PATH, REQUIRED_PRICE_TICKERS

ROOT = Path(__file__).resolve().parents[1]
HOLDINGS_PATH = ROOT / "data" / "config" / "holdings.csv"


def _openbb_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(DEFAULT_PRICE_PATH)
    df["source"] = "openbb_yfinance"
    return df.copy(), df.copy()


def test_complete_panel_creates_item_per_required_ticker(tmp_path):
    raw, proc = _openbb_frames()
    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "proc.csv"
    raw.to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    snap = build_market_monitor_snapshot(
        raw_path,
        proc_path,
        holdings_path=HOLDINGS_PATH,
        monitor_tickers=REQUIRED_PRICE_TICKERS,
    )
    assert snap["ticker_count"] == len(REQUIRED_PRICE_TICKERS)
    assert len(snap["items"]) == len(REQUIRED_PRICE_TICKERS)
    assert snap["official_risk_decision_allowed"] is False
    assert "VIX" in {item["ticker"] for item in snap["items"]}


def test_vix_newer_date_is_newer_than_official_eod(tmp_path):
    raw, proc = _openbb_frames()
    official = proc["date"].max()
    vix_latest = raw[(raw["ticker"] == "VIX") & (raw["date"] == official)].iloc[0].copy()
    vix_latest["date"] = "2099-12-31"
    raw = pd.concat([raw, pd.DataFrame([vix_latest])], ignore_index=True)
    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "proc.csv"
    raw.to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    snap = build_market_monitor_snapshot(raw_path, proc_path)
    items = {i["ticker"]: i for i in snap["items"]}
    assert items["VIX"]["timing_status"] == "newer_than_official_eod"
    assert items["SPY"]["timing_status"] == "official_eod_aligned"


def test_stale_ticker_flagged(tmp_path):
    raw, proc = _openbb_frames()
    official = proc["date"].max()
    raw = raw[~((raw["ticker"] == "SPY") & (raw["date"] == official))].copy()
    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "proc.csv"
    raw.to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    snap = build_market_monitor_snapshot(raw_path, proc_path, stale_days_threshold=1)
    spy = next(i for i in snap["items"] if i["ticker"] == "SPY")
    assert spy["timing_status"] == "stale_vs_official_eod"
    assert spy["is_stale"] is True
    assert spy["stale_days"] > 0


def test_fewer_than_two_observations_null_return_and_warning(tmp_path):
    raw, proc = _openbb_frames()
    raw = raw[raw["ticker"] != "USO"].copy()
    uso_one = raw[raw["ticker"] == "SPY"].head(1).copy()
    uso_one["ticker"] = "USO"
    raw = pd.concat([raw, uso_one], ignore_index=True)
    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "proc.csv"
    raw.to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    snap = build_market_monitor_snapshot(raw_path, proc_path)
    uso = next(i for i in snap["items"] if i["ticker"] == "USO")
    assert uso["latest_return"] is None
    assert uso["latest_return_pct"] is None
    assert "insufficient" in uso["display_warning"].lower()


def test_missing_raw_path_fails(tmp_path):
    _, proc = _openbb_frames()
    proc_path = tmp_path / "proc.csv"
    proc.to_csv(proc_path, index=False)
    with pytest.raises(FileNotFoundError, match="raw"):
        build_market_monitor_snapshot(tmp_path / "missing_raw.csv", proc_path)


def test_missing_processed_path_fails(tmp_path):
    raw, _ = _openbb_frames()
    raw_path = tmp_path / "raw.csv"
    raw.to_csv(raw_path, index=False)
    with pytest.raises(FileNotFoundError, match="processed"):
        build_market_monitor_snapshot(raw_path, tmp_path / "missing_proc.csv")


def test_raw_bad_schema_fails_cleanly(tmp_path):
    raw, proc = _openbb_frames()
    raw_path = tmp_path / "raw_bad.csv"
    proc_path = tmp_path / "proc.csv"
    raw.drop(columns=["source"]).to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    with pytest.raises(ValueError, match="raw price columns"):
        build_market_monitor_snapshot(raw_path, proc_path)


def test_raw_bad_close_fails_loudly(tmp_path):
    raw, proc = _openbb_frames()
    raw["close"] = raw["close"].astype(object)
    raw.loc[raw.index[0], "close"] = "bad"
    raw_path = tmp_path / "raw_bad_close.csv"
    proc_path = tmp_path / "proc.csv"
    raw.to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    with pytest.raises(ValueError, match="non-numeric close"):
        build_market_monitor_snapshot(raw_path, proc_path)


def test_processed_anchor_must_be_official_eod_ready(tmp_path):
    raw, proc = _openbb_frames()
    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "proc_bad.csv"
    raw.to_csv(raw_path, index=False)
    proc.drop(index=proc.index[0]).to_csv(proc_path, index=False)

    with pytest.raises(ValueError, match="official EOD panel"):
        build_market_monitor_snapshot(raw_path, proc_path)


def test_holdings_metadata_joins(tmp_path):
    raw, proc = _openbb_frames()
    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "proc.csv"
    raw.to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    snap = build_market_monitor_snapshot(raw_path, proc_path, holdings_path=HOLDINGS_PATH)
    spy = next(i for i in snap["items"] if i["ticker"] == "SPY")
    assert spy["target_weight"] == pytest.approx(0.10)
    assert spy["asset_class"] == "Equity"
    vix = next(i for i in snap["items"] if i["ticker"] == "VIX")
    assert vix["target_weight"] == 0.0
    assert vix["risk_bucket"] == "monitor_only"


def test_default_monitor_uses_broad_etf_universe(tmp_path):
    raw, proc = _openbb_frames()
    extra = []
    last_date = raw["date"].max()
    spy_row = raw[(raw["ticker"] == "SPY") & (raw["date"] == last_date)].iloc[0].copy()
    for ticker in ["XLK", "XLF", "EFA", "QUAL"]:
        row = spy_row.copy()
        row["ticker"] = ticker
        extra.append(row)
    raw = pd.concat([raw, pd.DataFrame(extra)], ignore_index=True)
    raw_path = tmp_path / "raw.csv"
    proc_path = tmp_path / "proc.csv"
    raw.to_csv(raw_path, index=False)
    proc.to_csv(proc_path, index=False)

    snap = build_market_monitor_snapshot(raw_path, proc_path, holdings_path=HOLDINGS_PATH)
    tickers = {item["ticker"] for item in snap["items"]}
    assert len(tickers) >= 39
    assert {"XLK", "XLF", "EFA", "QUAL", "VIX"}.issubset(tickers)
    assert "VXX" not in tickers
