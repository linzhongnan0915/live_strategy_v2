"""Tests for live polling orchestration (no network)."""

import json

import pandas as pd

from scripts import run_live_polling
from src.portfolio.metrics_builder import DEFAULT_PRICE_PATH, REQUIRED_PRICE_TICKERS


def _openbb_sample_frame():
    df = pd.read_csv(DEFAULT_PRICE_PATH)
    df["source"] = "openbb_yfinance"
    return df


def test_live_poll_cycle_writes_shared_artifacts(tmp_path, monkeypatch):
    proc = _openbb_sample_frame()
    proc_path = tmp_path / "processed.csv"
    proc.to_csv(proc_path, index=False)

    monkeypatch.setattr(
        run_live_polling,
        "_resolve_live_tickers",
        lambda: list(REQUIRED_PRICE_TICKERS),
    )
    monkeypatch.setattr(
        run_live_polling,
        "fetch_openbb_price_history",
        lambda *args, **kwargs: _openbb_sample_frame(),
    )
    monkeypatch.setattr(
        run_live_polling,
        "fetch_dxy_snapshot",
        lambda *args, **kwargs: {"status": "success", "current": 100},
    )
    monkeypatch.setattr(
        run_live_polling,
        "fetch_econ_upcoming_snapshot",
        lambda *args, **kwargs: {"status": "success", "event_count": 0, "events": []},
    )

    status = run_live_polling.run_poll_cycle(
        cycle=1,
        provider="yfinance",
        interval_seconds=30,
        lookback_days=10,
        live_raw_path=tmp_path / "live_raw.csv",
        processed_path=proc_path,
        monitor_path=tmp_path / "monitor.json",
        watchlist_path=tmp_path / "watchlist.json",
        status_path=tmp_path / "status.json",
        news_risk_path=tmp_path / "news.json",
        macro_context_path=tmp_path / "macro.json",
    )

    assert status["status"] == "success"
    assert status["row_count"] > 0
    assert (tmp_path / "live_raw.csv").exists()
    assert (tmp_path / "monitor.json").exists()
    assert (tmp_path / "watchlist.json").exists()
    assert (tmp_path / "news.json").exists()
    assert (tmp_path / "macro.json").exists()
    saved = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert saved["official_risk_decision_allowed"] is False
    assert saved["data_mode"] == "live_polling_openbb_yfinance_prototype"


def test_live_poll_cycle_writes_failed_status_without_crashing(tmp_path, monkeypatch):
    proc = _openbb_sample_frame()
    proc_path = tmp_path / "processed.csv"
    proc.to_csv(proc_path, index=False)

    monkeypatch.setattr(
        run_live_polling,
        "_resolve_live_tickers",
        lambda: list(REQUIRED_PRICE_TICKERS),
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(run_live_polling, "fetch_openbb_price_history", _raise)

    status = run_live_polling.run_poll_cycle(
        cycle=2,
        provider="yfinance",
        interval_seconds=30,
        lookback_days=10,
        live_raw_path=tmp_path / "live_raw.csv",
        processed_path=proc_path,
        monitor_path=tmp_path / "monitor.json",
        watchlist_path=tmp_path / "watchlist.json",
        status_path=tmp_path / "status.json",
        news_risk_path=tmp_path / "news.json",
        macro_context_path=tmp_path / "macro.json",
    )

    assert status["status"] == "failed"
    assert "provider unavailable" in status["error"]
    saved = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
    assert saved["official_risk_decision_allowed"] is False


def test_live_poll_cycle_supports_news_only_one_second_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run_live_polling,
        "_resolve_live_tickers",
        lambda: list(REQUIRED_PRICE_TICKERS),
    )
    monkeypatch.setattr(
        run_live_polling,
        "fetch_dxy_snapshot",
        lambda *args, **kwargs: {"status": "success", "current": 100},
    )
    monkeypatch.setattr(
        run_live_polling,
        "fetch_econ_upcoming_snapshot",
        lambda *args, **kwargs: {"status": "success", "event_count": 0, "events": []},
    )

    status = run_live_polling.run_poll_cycle(
        cycle=3,
        provider="yfinance",
        interval_seconds=1,
        lookback_days=10,
        live_raw_path=tmp_path / "live_raw.csv",
        processed_path=tmp_path / "processed.csv",
        monitor_path=tmp_path / "monitor.json",
        watchlist_path=tmp_path / "watchlist.json",
        status_path=tmp_path / "status.json",
        news_risk_path=tmp_path / "news.json",
        macro_context_path=tmp_path / "macro.json",
        market_data_mode="none",
    )

    assert status["status"] == "success"
    assert status["row_count"] == 0
    assert status["news_status"] == "not_configured"
    assert (tmp_path / "news.json").exists()
    assert (tmp_path / "macro.json").exists()
