"""Tests for baseline ETF strategy sleeve backtester."""

import json

import pandas as pd

from src.backtesting.strategy_backtester import (
    REQUIRED_BACKTEST_COLUMNS,
    backtest_all_strategies,
    build_backtest_snapshot,
)


def test_backtester_outputs_at_least_20_rows():
    results, meta = backtest_all_strategies()
    assert len(results) >= 20
    assert meta["strategy_count"] == len(results)
    assert meta["prototype_baseline_backtest"] is True


def test_backtester_required_columns_exist():
    results, _ = backtest_all_strategies()
    assert list(results.columns) == REQUIRED_BACKTEST_COLUMNS


def test_win_rates_between_zero_and_one_when_available():
    results, _ = backtest_all_strategies()
    for col in ("win_rate_daily", "win_rate_monthly"):
        vals = pd.to_numeric(results[col], errors="coerce").dropna()
        assert ((vals >= 0) & (vals <= 1)).all()


def test_max_drawdown_non_positive():
    results, _ = backtest_all_strategies()
    vals = pd.to_numeric(results["max_drawdown"], errors="coerce").fillna(0)
    assert (vals <= 0).all()


def test_missing_coverage_strategies_do_not_disappear():
    results, meta = backtest_all_strategies()
    assert len(results) == meta["strategy_count"]
    assert "price_coverage_status" in results.columns
    assert meta["insufficient_coverage_count"] >= 0


def test_snapshot_json_contract(tmp_path):
    out = tmp_path / "backtest.json"
    snapshot = build_backtest_snapshot()
    out.write_text(json.dumps(snapshot), encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["prototype_baseline_backtest"] is True
    assert loaded["signal_conditioned_alpha_validation"] is False
    assert loaded["official_risk_decision_allowed"] is False
    assert len(loaded["items"]) >= 20


def test_no_trade_recommendation_language():
    snapshot = build_backtest_snapshot()
    text = json.dumps(snapshot).lower()
    banned = ["buy ", "sell ", "execute order", "trade instruction"]
    assert not any(term in text for term in banned)
