"""Tests for actionable alert hierarchy and subsumed context."""

import json

from src.portfolio.metrics_builder import build_metrics_snapshot
from src.regime.rule_engine import (
    run_rule_engine,
    subsumed_alert_explanation,
)
from src.reporting.after_market_report import (
    _derive_overall_escalation,
    _human_review_count,
    build_after_market_report,
)


def _liquidity_and_credit_metrics() -> dict:
    return {
        "VIX level": 30.0,
        "VIX change": 4.0,
        "SPY return": -0.02,
        "QQQ return": -0.02,
        "IWM return": -0.02,
        "TLT return": -0.01,
        "HYG return": -0.02,
        "LQD return": 0.01,
        "GLD return": 0.01,
        "USO return": 0.01,
        "UUP return": 0.01,
        "HYG vs LQD relative return": -0.035,
        "SPY drawdown": -0.03,
        "portfolio drawdown": -0.02,
        "portfolio VaR": 0.5,
        "headline severity": 0,
        "cross-asset confirmation count": 0,
        "strategy return deviation": 0,
    }


def test_liquidity_and_credit_hierarchy_primary_vs_subsumed(tmp_path):
    path = tmp_path / "liq_credit.json"
    path.write_text(
        json.dumps(
            {
                "as_of_date": "2026-04-14",
                "data_source": "test",
                "metrics": _liquidity_and_credit_metrics(),
            }
        ),
        encoding="utf-8",
    )
    result = run_rule_engine(metrics_path=path)
    primary_ids = set(result["primary_alerts"]["rule_id"].astype(str))
    subsumed_ids = set(result["subsumed_alerts"]["rule_id"].astype(str))
    all_ids = set(result["alerts"]["rule_id"].astype(str))

    assert "liquidity_stress" in primary_ids
    assert "credit_stress" in subsumed_ids
    assert "credit_stress" in all_ids
    assert result["subsumed_alerts"].iloc[0]["subsumed_by"] == "liquidity_stress"
    assert result["subsumed_alerts"].iloc[0]["display_group"] == "subsumed_context"
    assert (
        subsumed_alert_explanation("credit_stress", "liquidity_stress")
        == "credit_stress is shown as context because liquidity_stress is the "
        "dominant escalation."
    )


def test_credit_stress_alone_stays_primary(tmp_path):
    metrics = _liquidity_and_credit_metrics()
    metrics["VIX level"] = 22.0
    metrics["HYG vs LQD relative return"] = -0.02
    path = tmp_path / "credit_only.json"
    path.write_text(
        json.dumps({"as_of_date": "2026-04-14", "data_source": "test", "metrics": metrics}),
        encoding="utf-8",
    )
    result = run_rule_engine(metrics_path=path)
    assert "credit_stress" in set(result["primary_alerts"]["rule_id"].astype(str))
    assert result["subsumed_alerts"].empty


def test_all_alerts_includes_both_when_both_fire(tmp_path):
    path = tmp_path / "both.json"
    path.write_text(
        json.dumps(
            {
                "as_of_date": "2026-04-14",
                "data_source": "test",
                "metrics": _liquidity_and_credit_metrics(),
            }
        ),
        encoding="utf-8",
    )
    result = run_rule_engine(metrics_path=path)
    all_ids = set(result["all_alerts"]["rule_id"].astype(str))
    assert "liquidity_stress" in all_ids
    assert "credit_stress" in all_ids


def test_escalation_red_uses_liquidity_primary(tmp_path):
    result = run_rule_engine(
        metrics_path=_write_metrics(tmp_path, _liquidity_and_credit_metrics())
    )
    assert _derive_overall_escalation(result["primary_alerts"]) == "red"
    assert _human_review_count(result["alerts"]) >= _human_review_count(
        result["primary_alerts"]
    )
    assert _human_review_count(result["primary_alerts"]) >= 1


def test_computed_sample_credit_stress_remains_primary(tmp_path):
    snapshot = build_metrics_snapshot(as_of_date="2026-04-14")
    result = run_rule_engine(metrics_path=_write_snapshot(tmp_path, snapshot))
    assert "credit_stress" in set(result["primary_alerts"]["rule_id"].astype(str))
    assert "liquidity_stress" not in set(result["primary_alerts"]["rule_id"].astype(str))
    assert result["subsumed_alerts"].empty


def test_report_human_review_excludes_subsumed(monkeypatch, tmp_path):
    engine = run_rule_engine(
        metrics_path=_write_metrics(tmp_path, _liquidity_and_credit_metrics())
    )
    monkeypatch.setattr(
        "src.reporting.after_market_report._run_rule_engine_for_snapshot",
        lambda snapshot, config_dir=None: engine,
    )
    strat = build_after_market_report(as_of_date="2026-04-14")["strategy_alert_view"]
    assert strat["human_review_required_count"] == len(
        strat["primary_actionable_alerts"]
    )
    assert "dominant escalation" in " ".join(strat.get("subsumed_alert_notes", []))


def _write_metrics(tmp_path, metrics: dict):
    path = tmp_path / "m.json"
    path.write_text(
        json.dumps({"as_of_date": "2026-04-14", "data_source": "test", "metrics": metrics}),
        encoding="utf-8",
    )
    return path


def _write_snapshot(tmp_path, snapshot: dict):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path
