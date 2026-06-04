"""Tests for WFO-style strategy evaluation."""

import json

import numpy as np
import pandas as pd

from src.backtesting.strategy_backtester import (
    WFO_RESULT_COLUMNS,
    build_walk_forward_snapshot,
    parse_target_etfs,
    walk_forward_evaluate_strategies,
)
from src.data.config_loader import load_strategy_library
from src.external.openbb_client import PRICE_HISTORY_COLUMNS


def _write_long_price_panel(path):
    strategies = load_strategy_library()
    tickers = sorted(
        {
            ticker
            for value in strategies["target_etfs"].astype(str)
            for ticker in parse_target_etfs(value)
        }
    )
    dates = pd.bdate_range("2016-01-04", "2025-12-31")
    rows = []
    for i, ticker in enumerate(tickers):
        drift = 0.00008 + (i % 7) * 0.00001
        wave = np.sin(np.arange(len(dates)) / (35 + i % 5)) * 0.0007
        returns = drift + wave
        close = 50 + i
        for date, ret in zip(dates, returns):
            close *= 1.0 + float(ret)
            rows.append(
                {
                    "date": date.date().isoformat(),
                    "ticker": ticker,
                    "close": round(close, 6),
                    "source": "openbb_yfinance",
                }
            )
    pd.DataFrame(rows, columns=PRICE_HISTORY_COLUMNS).to_csv(path, index=False)


def test_walk_forward_outputs_strategy_rows(tmp_path):
    price_path = tmp_path / "long_prices.csv"
    _write_long_price_panel(price_path)

    results, meta = walk_forward_evaluate_strategies(
        price_path=price_path,
        train_years=3,
        test_months=12,
        step_months=12,
        top_n=5,
    )

    assert list(results.columns) == WFO_RESULT_COLUMNS
    assert len(results) >= 20
    assert meta["walk_forward_optimization"] is True
    assert meta["window_count"] >= 5
    assert meta["approx_years"] >= 9
    assert results["wfo_score"].between(0, 1).all()
    assert meta["duplicate_ticker_date_count"] == 0
    assert meta["rolling_window_summary"]["no_lookahead_rule"].startswith("each train_end")


def test_walk_forward_uses_oos_windows_without_trade_authorization(tmp_path):
    price_path = tmp_path / "long_prices.csv"
    _write_long_price_panel(price_path)

    snapshot = build_walk_forward_snapshot(
        price_path=price_path,
        train_years=3,
        test_months=12,
        step_months=12,
        top_n=5,
    )

    assert snapshot["official_risk_decision_allowed"] is False
    assert snapshot["signal_conditioned_alpha_validation"] is False
    assert snapshot["windows"]
    assert len(snapshot["window_schedule"]) == snapshot["window_count"]
    first_window = snapshot["windows"][0]
    assert first_window["train_end"] < first_window["test_start"]
    assert first_window["selected_top_n"] in {True, False}
    assert snapshot["window_schedule"][0]["train_end"] < snapshot["window_schedule"][0]["test_start"]


def test_walk_forward_default_rolls_forward_more_often_than_annual(tmp_path):
    price_path = tmp_path / "long_prices.csv"
    _write_long_price_panel(price_path)

    quarterly = build_walk_forward_snapshot(price_path=price_path, train_years=3)
    annual = build_walk_forward_snapshot(
        price_path=price_path,
        train_years=3,
        step_months=12,
    )

    assert quarterly["step_months"] == 3
    assert quarterly["window_count"] > annual["window_count"]
    starts = [row["test_start"] for row in quarterly["window_schedule"][:3]]
    assert starts == sorted(starts)


def test_walk_forward_snapshot_json_contract(tmp_path):
    price_path = tmp_path / "long_prices.csv"
    _write_long_price_panel(price_path)
    out = tmp_path / "wfo.json"

    snapshot = build_walk_forward_snapshot(price_path=price_path, train_years=3)
    out.write_text(json.dumps(snapshot), encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))

    assert loaded["data_mode"] == "walk_forward_strategy_evaluation"
    assert loaded["items"]
    assert loaded["items"][0]["wfo_rank"] == 1
    assert "not a trade recommendation" in loaded["note"].lower()


def test_walk_forward_reports_no_windows_on_short_history(tmp_path):
    short_path = tmp_path / "short_prices.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-01-01",
                "ticker": "SPY",
                "close": 100.0,
                "source": "openbb_yfinance",
            },
            {
                "date": "2026-01-02",
                "ticker": "SPY",
                "close": 101.0,
                "source": "openbb_yfinance",
            },
        ],
        columns=PRICE_HISTORY_COLUMNS,
    ).to_csv(short_path, index=False)

    results, meta = walk_forward_evaluate_strategies(price_path=short_path)

    assert results.empty
    assert meta["window_count"] == 0
    assert "fetch longer history" in meta["note"].lower()


def test_monitor_only_vol_tickers_do_not_drive_wfo_returns(tmp_path):
    price_path = tmp_path / "long_prices.csv"
    _write_long_price_panel(price_path)

    results, _ = walk_forward_evaluate_strategies(
        price_path=price_path,
        train_years=3,
        test_months=12,
        step_months=12,
        top_n=5,
    )
    vol_row = results[results["strategy_id"] == "volatility_spike_monitor_sleeve"].iloc[0]

    assert "VIX" not in vol_row["available_price_etfs"].split(";")
    assert "VXX" not in vol_row["available_price_etfs"].split(";")
    assert "VIX" in vol_row["missing_price_etfs"].split(";")
    assert "VXX" in vol_row["missing_price_etfs"].split(";")
