"""Tests for prototype regime rule engine dry-run."""

import json

import pandas as pd
import pytest

from src.data.config_loader import load_all_configs
from src.portfolio.metrics_builder import build_metrics_snapshot
from src.regime.rule_engine import (
    ALERT_COLUMNS,
    DEFAULT_METRICS_PATH,
    INFORMATIONAL_CONTEXT_MODE_CAUTION,
    INFORMATIONAL_CONTEXT_MODE_NORMAL,
    INFORMATIONAL_CONTEXT_MODE_STRESS,
    PROJECT_ROOT,
    aggregate_rule_alerts,
    compare_metric,
    derive_alert_escalation,
    derive_informational_context_mode,
    derive_informational_context_note,
    evaluate_thresholds,
    load_metrics_json,
    map_escalation_level,
    rule_passes_confirmation_policy,
    rule_passes_threshold_gate,
    run_rule_engine,
    split_actionable_and_informational_alerts,
)

MOCK_METRICS_PATH = PROJECT_ROOT / "data" / "samples" / "mock_daily_metrics.json"


@pytest.mark.parametrize(
    "value,operator,threshold,expected",
    [
        (5.0, ">", 4.0, True),
        (4.0, ">=", 4.0, True),
        (3.0, "<", 4.0, True),
        (4.0, "<=", 4.0, True),
        (4.0, "==", 4.0, True),
        (4.0, "!=", 3.0, True),
        (3.0, ">", 4.0, False),
    ],
)
def test_compare_metric(value, operator, threshold, expected):
    assert compare_metric(value, operator, threshold) is expected


def test_compare_metric_invalid_operator():
    with pytest.raises(ValueError, match="Unsupported operator"):
        compare_metric(1.0, "<>", 0.0)


@pytest.mark.parametrize(
    "priority,expected",
    [
        (1, "green"),
        (2, "green"),
        (3, "yellow"),
        (4, "red"),
        (5, "red"),
    ],
)
def test_map_escalation_level(priority, expected):
    assert map_escalation_level(priority) == expected


def test_run_rule_engine_includes_escalation_level():
    result = run_rule_engine()
    alerts = result["alerts"]
    assert "escalation_level" in alerts.columns
    assert set(alerts["escalation_level"].unique()).issubset({"green", "yellow", "red"})


def test_all_red_alerts_require_human_review():
    result = run_rule_engine()
    alerts = result["alerts"]
    red = alerts[alerts["escalation_level"] == "red"]
    assert not red.empty, "Mock snapshot should produce at least one red alert"
    assert red["requires_human_review"].all()


def test_mock_stress_produces_at_least_one_red_alert():
    result = run_rule_engine()
    assert (result["alerts"]["escalation_level"] == "red").any()


def test_mock_daily_metrics_json_loads():
    payload = load_metrics_json(DEFAULT_METRICS_PATH)
    assert payload["as_of_date"] == "2026-06-02"
    assert "VIX level" in payload["metrics"]


def test_evaluate_thresholds_returns_hits():
    configs = load_all_configs()
    payload = load_metrics_json(DEFAULT_METRICS_PATH)
    hits, missing = evaluate_thresholds(payload["metrics"], configs["regime_thresholds"])
    assert not hits.empty
    assert hits["hit"].any()
    assert (hits.loc[hits["hit"], "threshold_id"].nunique()) >= 1


def test_run_rule_engine_returns_at_least_one_alert():
    result = run_rule_engine()
    assert len(result["alerts"]) >= 1


def test_run_rule_engine_alerts_sorted_by_priority_desc():
    result = run_rule_engine()
    alerts = result["alerts"]
    if len(alerts) < 2:
        pytest.skip("Need multiple alerts to test sort order")
    priorities = alerts["priority"].tolist()
    assert priorities == sorted(priorities, reverse=True)


def test_priority_gte_3_requires_human_review():
    result = run_rule_engine()
    alerts = result["alerts"]
    high = alerts[alerts["priority"] >= 3]
    if high.empty:
        pytest.fail("Expected at least one priority >= 3 alert from mock snapshot")
    assert high["requires_human_review"].all()


def test_missing_metrics_reported_not_silently_ignored():
    configs = load_all_configs()
    partial = {"VIX level": 25.0}
    hits, missing = evaluate_thresholds(partial, configs["regime_thresholds"])
    assert len(missing) > 0
    assert hits.loc[hits["missing"], "hit"].eq(False).all()
    result = run_rule_engine()
    assert isinstance(result["missing_metrics"], list)


def test_run_rule_engine_triggers_expected_rule_families():
    result = run_rule_engine(metrics_path=MOCK_METRICS_PATH)
    rule_ids = set(result["alerts"]["rule_id"].astype(str))
    expected_any = {
        "high_volatility",
        "risk_off",
        "geopolitical_shock",
        "drawdown_breach",
    }
    assert expected_any.intersection(rule_ids), (
        f"Expected mock to trigger some of {expected_any}; got {rule_ids}"
    )


def test_computed_snapshot_does_not_trigger_geopolitical_shock(tmp_path):
    snapshot = build_metrics_snapshot()
    assert snapshot["metrics"]["headline severity"] == 0
    path = tmp_path / "computed.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    result = run_rule_engine(metrics_path=path)
    rule_ids = set(result["alerts"]["rule_id"].astype(str))
    assert "geopolitical_shock" not in rule_ids


def test_mock_snapshot_triggers_geopolitical_shock():
    result = run_rule_engine(metrics_path=MOCK_METRICS_PATH)
    rule_ids = set(result["alerts"]["rule_id"].astype(str))
    assert "geopolitical_shock" in rule_ids


def test_geopolitical_gate_requires_headline_and_cross_asset():
    assert not rule_passes_confirmation_policy(
        "geopolitical_shock", {"gld_5d_safe_haven"}
    )
    assert not rule_passes_confirmation_policy(
        "geopolitical_shock",
        {"cross_asset_confirm_min", "gld_5d_safe_haven"},
    )
    assert rule_passes_confirmation_policy(
        "geopolitical_shock",
        {"headline_severity_min", "cross_asset_confirm_min"},
    )
    assert rule_passes_threshold_gate(
        "geopolitical_shock",
        {
            "headline_severity_min",
            "cross_asset_confirm_min",
            "gld_5d_safe_haven",
        },
    )


def _base_metrics() -> dict[str, float | int]:
    return {
        "VIX level": 15.0,
        "VIX change": 0.5,
        "SPY return": 0.01,
        "QQQ return": 0.01,
        "IWM return": 0.01,
        "TLT return": 0.01,
        "IEF return": 0.01,
        "SHY return": 0.01,
        "HYG return": 0.01,
        "LQD return": 0.01,
        "TIP return": 0.01,
        "USO return": 0.01,
        "UUP return": 0.01,
        "HYG vs LQD relative return": 0.0,
        "SPY drawdown": -0.01,
        "portfolio drawdown": -0.01,
        "portfolio VaR": 0.5,
        "headline severity": 0,
        "cross-asset confirmation count": 0,
        "strategy return deviation": 0,
    }


def _all_alerts_for(metrics: dict) -> pd.DataFrame:
    configs = load_all_configs()
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    return aggregate_rule_alerts(hits, configs["regime_rules"])


def _alerts_for(metrics: dict) -> pd.DataFrame:
    """Actionable alerts only (yellow/red), matching run_rule_engine alerts key."""
    actionable, _ = split_actionable_and_informational_alerts(_all_alerts_for(metrics))
    return actionable


def _informational_alerts_for(metrics: dict) -> pd.DataFrame:
    _, informational = split_actionable_and_informational_alerts(_all_alerts_for(metrics))
    return informational


def test_risk_on_not_from_spy_alone_when_vix_elevated():
    metrics = _base_metrics()
    metrics["SPY return"] = 0.02
    metrics["VIX level"] = 24.0
    alerts = _alerts_for(metrics)
    assert "risk_on" not in set(alerts["rule_id"].astype(str))


def test_risk_on_triggers_when_spy_positive_and_vix_calm():
    metrics = _base_metrics()
    metrics["SPY return"] = 0.02
    metrics["VIX level"] = 16.0
    metrics["UUP return"] = 0.005
    metrics["TIP return"] = 0.005
    informational = _informational_alerts_for(metrics)
    assert "risk_on" in set(informational["rule_id"].astype(str))
    assert "risk_on" not in set(_alerts_for(metrics)["rule_id"].astype(str))


def test_low_volatility_blocked_when_vix_change_spike():
    metrics = _base_metrics()
    metrics["VIX level"] = 14.0
    metrics["VIX change"] = 4.0
    alerts = _alerts_for(metrics)
    assert "low_volatility" not in set(alerts["rule_id"].astype(str))


def test_credit_calm_blocked_when_vix_elevated():
    metrics = _base_metrics()
    metrics["HYG vs LQD relative return"] = 0.0
    metrics["VIX level"] = 24.0
    alerts = _alerts_for(metrics)
    assert "credit_calm" not in set(alerts["rule_id"].astype(str))


def test_inflation_pressure_not_from_tip_alone():
    metrics = _base_metrics()
    metrics["TIP return"] = 0.02
    alerts = _alerts_for(metrics)
    assert "inflation_pressure" not in set(alerts["rule_id"].astype(str))


def test_inflation_pressure_triggers_with_tip_and_uso():
    metrics = _base_metrics()
    metrics["TIP return"] = 0.02
    metrics["USO return"] = 0.04
    alerts = _alerts_for(metrics)
    assert "inflation_pressure" in set(alerts["rule_id"].astype(str))


def test_inflation_pressure_triggers_with_tip_and_tlt():
    metrics = _base_metrics()
    metrics["TIP return"] = 0.02
    metrics["TLT return"] = -0.03
    alerts = _alerts_for(metrics)
    assert "inflation_pressure" in set(alerts["rule_id"].astype(str))


def test_normal_scenario_no_yellow_or_red_rule_alerts():
    metrics = _base_metrics()
    metrics["VIX level"] = 14.0
    metrics["VIX change"] = 1.0
    metrics["SPY return"] = 0.01
    metrics["HYG vs LQD relative return"] = 0.0
    metrics["UUP return"] = 0.005
    metrics["TIP return"] = 0.005
    configs = load_all_configs()
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    all_alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    actionable, informational = split_actionable_and_informational_alerts(all_alerts)
    assert actionable.empty
    if not all_alerts.empty:
        assert (informational["escalation_level"] == "green").all()


def test_risk_off_not_triggered_from_vix_alone():
    configs = load_all_configs()
    metrics = _base_metrics()
    metrics["VIX level"] = 24.0
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    assert "risk_off" not in set(alerts["rule_id"].astype(str))


def test_risk_off_triggers_with_vix_and_equity_weakness():
    configs = load_all_configs()
    metrics = _base_metrics()
    metrics["VIX level"] = 24.0
    metrics["SPY return"] = -0.03
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    risk_off = alerts[alerts["rule_id"] == "risk_off"]
    assert len(risk_off) == 1
    assert risk_off.iloc[0]["escalation_level"] == "yellow"


def test_risk_off_not_red_from_portfolio_limit_thresholds_in_snapshot():
    level = derive_alert_escalation(
        "risk_off",
        4,
        {"risk_off_vix_min", "risk_off_spy_return_max"},
        {"high", "medium"},
        {
            "risk_off_vix_min",
            "risk_off_spy_return_max",
            "portfolio_drawdown_limit",
            "portfolio_var_ratio",
        },
    )
    assert level == "yellow"


def test_risk_off_red_when_spy_drawdown_also_hits():
    configs = load_all_configs()
    metrics = _base_metrics()
    metrics["VIX level"] = 24.0
    metrics["SPY drawdown"] = -0.06
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    risk_off = alerts[alerts["rule_id"] == "risk_off"]
    assert len(risk_off) == 1
    assert risk_off.iloc[0]["escalation_level"] == "red"


def test_high_volatility_vix_24_maps_yellow():
    level = derive_alert_escalation(
        "high_volatility",
        4,
        {"vix_elevated_min", "vix_change_1d_elevated"},
        {"medium"},
    )
    assert level == "yellow"


def test_high_volatility_vix_30_alone_maps_yellow():
    level = derive_alert_escalation(
        "high_volatility",
        4,
        {"vix_high_min", "vix_elevated_min"},
        {"high", "medium"},
        {"vix_high_min", "vix_elevated_min"},
    )
    assert level == "yellow"


def test_high_volatility_vix_30_confirmed_maps_red():
    global_hits = {
        "vix_high_min",
        "vix_elevated_min",
        "vix_change_1d_elevated",
    }
    level = derive_alert_escalation(
        "high_volatility",
        4,
        {"vix_high_min", "vix_elevated_min"},
        {"high", "medium"},
        global_hits,
    )
    assert level == "red"


def test_var_watch_only_maps_yellow():
    level = derive_alert_escalation(
        "var_breach",
        5,
        {"portfolio_var_ratio_watch"},
        {"high"},
    )
    assert level == "yellow"


def test_var_ratio_maps_red():
    level = derive_alert_escalation(
        "var_breach",
        5,
        {"portfolio_var_ratio"},
        {"critical"},
    )
    assert level == "red"


def test_drawdown_warning_maps_yellow():
    level = derive_alert_escalation(
        "drawdown_breach",
        4,
        {"portfolio_drawdown_warning"},
        {"high"},
    )
    assert level == "yellow"


def test_drawdown_limit_maps_red():
    level = derive_alert_escalation(
        "drawdown_breach",
        4,
        {"portfolio_drawdown_limit"},
        {"critical"},
    )
    assert level == "red"


def test_high_volatility_vix_30_alone_via_metrics_yellow(tmp_path):
    metrics = _base_metrics()
    metrics["VIX level"] = 30.0
    metrics["VIX change"] = 1.0
    metrics["SPY return"] = 0.01
    alerts = _alerts_for(metrics)
    hv = alerts[alerts["rule_id"] == "high_volatility"]
    assert len(hv) == 1
    assert hv.iloc[0]["escalation_level"] == "yellow"


def test_credit_spread_alone_no_credit_stress():
    metrics = _base_metrics()
    metrics["HYG vs LQD relative return"] = -0.03
    metrics["VIX level"] = 15.0
    configs = load_all_configs()
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    assert "credit_stress" not in set(alerts["rule_id"].astype(str))


def test_credit_spread_vix20_red_credit_stress():
    metrics = _base_metrics()
    metrics["HYG vs LQD relative return"] = -0.03
    metrics["VIX level"] = 22.0
    alerts = _alerts_for(metrics)
    cs = alerts[alerts["rule_id"] == "credit_stress"]
    assert len(cs) == 1
    assert cs.iloc[0]["escalation_level"] == "red"


def test_var_ratio_at_limit_red_var_breach():
    metrics = _base_metrics()
    metrics["portfolio VaR"] = 1.05
    alerts = _alerts_for(metrics)
    var_row = alerts[alerts["rule_id"] == "var_breach"]
    assert len(var_row) == 1
    assert var_row.iloc[0]["escalation_level"] == "red"


def test_drawdown_at_limit_red_drawdown_breach():
    metrics = _base_metrics()
    metrics["portfolio drawdown"] = -0.09
    alerts = _alerts_for(metrics)
    dd = alerts[alerts["rule_id"] == "drawdown_breach"]
    assert len(dd) == 1
    assert dd.iloc[0]["escalation_level"] == "red"


def test_credit_stress_requires_both_thresholds():
    assert not rule_passes_confirmation_policy(
        "credit_stress", {"credit_stress_vix_min"}
    )
    assert rule_passes_confirmation_policy(
        "credit_stress",
        {"credit_stress_vix_min", "hyg_lqd_rel_20d_stress"},
    )


def test_liquidity_stress_requires_both_thresholds():
    assert not rule_passes_confirmation_policy(
        "liquidity_stress", {"vix_stress_liquidity"}
    )
    assert rule_passes_confirmation_policy(
        "liquidity_stress",
        {"liquidity_hyg_lqd_stress", "vix_stress_liquidity"},
    )


def test_computed_snapshot_calibrated_escalations(tmp_path):
    snapshot = build_metrics_snapshot()
    path = tmp_path / "computed.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    result = run_rule_engine(metrics_path=path)
    alerts = result["alerts"]
    by_rule = {row["rule_id"]: row for _, row in alerts.iterrows()}

    assert "geopolitical_shock" not in by_rule
    assert "risk_off" not in by_rule
    assert by_rule["high_volatility"]["escalation_level"] == "yellow"
    assert by_rule["credit_stress"]["escalation_level"] == "red"
    assert set(alerts["escalation_level"]) <= {"yellow", "red"}
    assert (alerts["escalation_level"] == "yellow").any()


def _synthetic_alert(rule_id: str, escalation_level: str) -> dict:
    requires_review = escalation_level in ("yellow", "red")
    return {
        "rule_id": rule_id,
        "regime_signal": "test",
        "risk_level": "high",
        "priority": 4,
        "escalation_level": escalation_level,
        "triggered_thresholds": "t1",
        "triggered_threshold_severities": "high",
        "affected_factors": "f1",
        "affected_strategies": "s1",
        "recommended_action": "monitor",
        "requires_human_review": requires_review,
        "notes": "test",
    }


def test_derive_informational_context_mode_normal_when_no_actionable():
    actionable = pd.DataFrame(columns=ALERT_COLUMNS)
    informational = pd.DataFrame([_synthetic_alert("risk_on", "green")])
    assert (
        derive_informational_context_mode(actionable, informational)
        == INFORMATIONAL_CONTEXT_MODE_NORMAL
    )


def test_derive_informational_context_mode_caution_on_yellow_only():
    actionable = pd.DataFrame([_synthetic_alert("high_volatility", "yellow")])
    informational = pd.DataFrame([_synthetic_alert("risk_on", "green")])
    assert (
        derive_informational_context_mode(actionable, informational)
        == INFORMATIONAL_CONTEXT_MODE_CAUTION
    )


def test_derive_informational_context_mode_stress_on_red():
    actionable = pd.DataFrame([_synthetic_alert("credit_stress", "red")])
    informational = pd.DataFrame([_synthetic_alert("low_volatility", "green")])
    assert (
        derive_informational_context_mode(actionable, informational)
        == INFORMATIONAL_CONTEXT_MODE_STRESS
    )


def test_derive_note_normal_empty_no_green_context():
    note = derive_informational_context_note(
        INFORMATIONAL_CONTEXT_MODE_NORMAL, False
    )
    assert note == "No green informational rule context is active."


def test_derive_note_caution_empty_no_green_displayed():
    note = derive_informational_context_note(
        INFORMATIONAL_CONTEXT_MODE_CAUTION, False
    )
    assert "no green informational context is displayed" in note.lower()


def test_derive_note_stress_empty_no_green_displayed():
    note = derive_informational_context_note(
        INFORMATIONAL_CONTEXT_MODE_STRESS, False
    )
    assert "no green informational context is displayed" in note.lower()
    assert "benign context present" not in note.lower()


def test_derive_note_stress_with_green_override_language():
    note = derive_informational_context_note(
        INFORMATIONAL_CONTEXT_MODE_STRESS, True
    )
    assert "benign context present" in note.lower()
    assert "overridden" in note.lower()


def test_run_rule_engine_includes_informational_context_fields(tmp_path):
    metrics = _base_metrics()
    metrics.update(
        {
            "VIX level": 14.0,
            "VIX change": 1.0,
            "SPY return": 0.01,
            "HYG vs LQD relative return": 0.0,
            "UUP return": 0.005,
            "TIP return": 0.005,
        }
    )
    path = tmp_path / "ctx.json"
    path.write_text(
        json.dumps(
            {"metrics": metrics, "as_of_date": "2026-04-14", "data_source": "test"}
        ),
        encoding="utf-8",
    )
    result = run_rule_engine(metrics_path=path)
    assert result["informational_context_mode"] == INFORMATIONAL_CONTEXT_MODE_NORMAL
    assert "green informational context is active" in result[
        "informational_context_note"
    ].lower()
    assert result["alerts"].empty
    assert not result["informational_alerts"].empty


def test_computed_replay_stress_note_when_no_informational_alerts(tmp_path):
    snapshot = build_metrics_snapshot(as_of_date="2026-04-14")
    path = tmp_path / "computed_stress.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    result = run_rule_engine(metrics_path=path)
    assert result["informational_alerts"].empty
    assert not result["alerts"].empty
    assert result["informational_context_mode"] == INFORMATIONAL_CONTEXT_MODE_STRESS
    note = result["informational_context_note"].lower()
    assert "no green informational context is displayed" in note
    assert "benign context present" not in note


def test_run_rule_engine_splits_actionable_and_informational():
    result = run_rule_engine()
    for key in ("alerts", "informational_alerts", "all_alerts"):
        assert key in result
    if not result["alerts"].empty:
        assert set(result["alerts"]["escalation_level"].astype(str)).issubset(
            {"yellow", "red"}
        )
    if not result["informational_alerts"].empty:
        assert set(
            result["informational_alerts"]["escalation_level"].astype(str)
        ) == {"green"}
    assert len(result["all_alerts"]) == len(result["alerts"]) + len(
        result["informational_alerts"]
    )


def test_green_only_fires_in_informational_not_alerts(tmp_path):
    metrics = _base_metrics()
    metrics["VIX level"] = 14.0
    metrics["VIX change"] = 1.0
    metrics["SPY return"] = 0.01
    metrics["HYG vs LQD relative return"] = 0.0
    metrics["UUP return"] = 0.005
    metrics["TIP return"] = 0.005
    path = tmp_path / "green_only.json"
    path.write_text(json.dumps({"metrics": metrics, "as_of_date": "2026-04-14", "data_source": "test"}), encoding="utf-8")
    result = run_rule_engine(metrics_path=path)
    assert result["alerts"].empty
    assert not result["informational_alerts"].empty
    assert (result["informational_alerts"]["escalation_level"] == "green").all()


def test_active_stress_actionable_separate_from_informational(tmp_path):
    snapshot = build_metrics_snapshot()
    path = tmp_path / "stress.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    result = run_rule_engine(metrics_path=path)
    assert not result["alerts"].empty
    assert (result["alerts"]["escalation_level"].isin(["yellow", "red"])).all()
    if not result["informational_alerts"].empty:
        assert (result["informational_alerts"]["escalation_level"] == "green").all()
    overlap = set(result["alerts"]["rule_id"]).intersection(
        set(result["informational_alerts"]["rule_id"])
    )
    assert not overlap


def test_run_rule_engine_actionable_sort_order_preserved(tmp_path):
    snapshot = build_metrics_snapshot()
    path = tmp_path / "sorted.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    result = run_rule_engine(metrics_path=path)
    actionable = result["alerts"]
    if len(actionable) >= 2:
        priorities = actionable["priority"].tolist()
        assert priorities == sorted(priorities, reverse=True)


def test_only_gld_hit_does_not_aggregate_geopolitical_alert():
    configs = load_all_configs()
    metrics = {
        "GLD return": 0.05,
        "headline severity": 0,
        "cross-asset confirmation count": 1,
        "VIX level": 15,
        "VIX change": 0,
        "SPY return": 0.01,
        "QQQ return": 0.01,
        "IWM return": 0.01,
        "TLT return": 0.01,
        "IEF return": 0.01,
        "SHY return": 0.01,
        "HYG return": 0.01,
        "LQD return": 0.01,
        "TIP return": 0.01,
        "USO return": 0.01,
        "UUP return": 0.01,
        "HYG vs LQD relative return": 0.0,
        "SPY drawdown": -0.01,
        "portfolio drawdown": -0.01,
        "portfolio VaR": 0.5,
        "strategy return deviation": 0,
    }
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    assert "geopolitical_shock" not in set(alerts["rule_id"].astype(str))
