"""Tests for metric-level status bands (Layer 1)."""

import json

import pytest

from src.data.config_loader import (
    METRIC_STATUS_POLICY_COLUMNS,
    load_all_configs,
    load_metric_status_policy,
)
from src.portfolio.metrics_builder import build_metrics_snapshot
from src.regime.metric_status import derive_metric_statuses, get_metric_status_summary
from src.regime.rule_engine import aggregate_rule_alerts, evaluate_thresholds, run_rule_engine


def _status_for(df, metric_name: str) -> str:
    row = df[df["metric_name"] == metric_name].iloc[0]
    return str(row["status"])


def test_metric_status_policy_loads_via_config_loader():
    configs = load_all_configs()
    assert "metric_status_policy" in configs
    df = load_metric_status_policy()
    assert list(df.columns) == METRIC_STATUS_POLICY_COLUMNS
    assert set(df["status"].astype(str).str.lower()) <= {"yellow", "red"}


def test_vix_24_metric_yellow():
    df = derive_metric_statuses({"VIX level": 24.0})
    assert _status_for(df, "VIX level") == "yellow"


def test_vix_31_metric_red():
    df = derive_metric_statuses({"VIX level": 31.0})
    assert _status_for(df, "VIX level") == "red"


def test_hyg_lqd_metric_yellow_credit_rule_needs_confirmation():
    metrics = {"HYG vs LQD relative return": -0.024, "VIX level": 15.0}
    df = derive_metric_statuses(metrics)
    assert _status_for(df, "HYG vs LQD relative return") == "yellow"

    configs = load_all_configs()
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    assert "credit_stress" not in set(alerts["rule_id"].astype(str))


def test_portfolio_var_metric_yellow_and_red():
    yellow_df = derive_metric_statuses({"portfolio VaR": 0.90})
    red_df = derive_metric_statuses({"portfolio VaR": 1.05})
    assert _status_for(yellow_df, "portfolio VaR") == "yellow"
    assert _status_for(red_df, "portfolio VaR") == "red"


def test_missing_policy_metric_status_missing_not_green():
    df = derive_metric_statuses({"VIX level": 24.0})
    row = df[df["metric_name"] == "portfolio VaR"].iloc[0]
    assert row["status"] == "missing"
    assert not bool(row["metric_available"])


def test_missing_count_and_list_in_summary():
    df = derive_metric_statuses({"VIX level": 12.0})
    summary = get_metric_status_summary(df)
    assert summary["missing_count"] >= 1
    assert "portfolio VaR" in summary["missing_metrics"]
    assert summary["green_count"] == 1


def test_green_count_excludes_missing_metrics():
    df = derive_metric_statuses({"VIX level": 12.0, "VIX change": 0.5})
    summary = get_metric_status_summary(df)
    assert summary["green_count"] == 2
    assert summary["missing_count"] == 8


def test_no_policy_hit_metric_green():
    df = derive_metric_statuses({"VIX level": 12.0, "VIX change": 0.5})
    assert _status_for(df, "VIX level") == "green"
    assert _status_for(df, "VIX change") == "green"


def test_computed_sample_has_at_least_one_yellow_metric():
    snapshot = build_metrics_snapshot()
    df = derive_metric_statuses(snapshot["metrics"])
    summary = get_metric_status_summary(df)
    assert summary["yellow_count"] >= 1


def test_derive_metric_statuses_is_not_rule_alerts():
    snapshot = build_metrics_snapshot()
    df = derive_metric_statuses(snapshot["metrics"])
    assert "rule_id" not in df.columns
    assert "escalation_level" not in df.columns


def test_metric_status_table_has_interpretation_and_related_rules():
    df = derive_metric_statuses({"VIX level": 24.0})
    row = df[df["metric_name"] == "VIX level"].iloc[0]
    assert row["interpretation"]
    assert row["related_rules"]
    assert "high_volatility" in str(row["related_rules"])


def test_computed_sample_metric_and_rule_summary(tmp_path):
    snapshot = build_metrics_snapshot()
    path = tmp_path / "computed.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    status_df = derive_metric_statuses(snapshot["metrics"])
    summary = get_metric_status_summary(status_df)
    engine = run_rule_engine(metrics_path=path)

    assert summary["yellow_count"] >= 1
    alerts = engine["alerts"]
    by_rule = {row["rule_id"]: row["escalation_level"] for _, row in alerts.iterrows()}
    if "high_volatility" in by_rule:
        assert by_rule["high_volatility"] == "yellow"
    if "credit_stress" in by_rule:
        assert by_rule["credit_stress"] == "red"
