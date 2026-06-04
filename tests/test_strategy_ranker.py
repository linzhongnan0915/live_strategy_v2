"""Tests for prototype strategy ranking."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.config_loader import (
    load_etf_universe,
    load_strategy_library,
    load_strategy_scoring_policy,
)
from src.strategy.strategy_ranker import build_ranking_snapshot, rank_strategies

ROOT = Path(__file__).resolve().parents[1]


def test_etf_universe_at_least_40_rows():
    df = load_etf_universe()
    assert len(df) >= 40


def test_strategy_library_at_least_20_rows():
    df = load_strategy_library()
    assert len(df) >= 20


def test_scoring_policy_weights_sum_to_one():
    policy = load_strategy_scoring_policy()
    assert abs(policy["weight"].astype(float).sum() - 1.0) < 1e-6


def test_ranker_outputs_at_least_20_rows():
    ranked, _ = rank_strategies()
    assert len(ranked) >= 20


def test_all_strategies_require_human_review():
    ranked, meta = rank_strategies()
    strategies = load_strategy_library()
    assert (strategies["human_review_required"].astype(str).str.upper() == "TRUE").all()
    assert meta["official_risk_decision_allowed"] is False


def test_build_snapshot_json(tmp_path):
    out = tmp_path / "ranking.json"
    snap = build_ranking_snapshot()
    assert snap["prototype_not_backtest"] is True
    assert len(snap["items"]) >= 20
    assert "overall_score" in snap["items"][0]
