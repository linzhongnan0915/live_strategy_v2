"""Tests for after-market risk report generator."""

from pathlib import Path

import pytest

from src.reporting.after_market_report import (
    FORBIDDEN_PHRASES,
    MARKDOWN_HEADINGS,
    REQUIRED_SECTIONS,
    build_after_market_report,
    render_markdown_report,
    write_after_market_report,
)
EARLY_AS_OF = "2026-04-01"
LATE_AS_OF = "2026-04-14"

def _mojibake_fragments() -> tuple[str, ...]:
    return (
        "\u922b",
        "\u9225",
        "\u922e",
        "\u9229",
        "\ufffd",
        "\u6522",
        "\u2014",
        "\u2013",
    )


def _assert_no_mojibake(text: str) -> None:
    for fragment in _mojibake_fragments():
        assert fragment not in text, f"found mojibake fragment: {fragment!r}"


def test_rendered_markdown_has_no_mojibake():
    md = render_markdown_report(build_after_market_report())
    _assert_no_mojibake(md)


def test_governance_notes_have_no_mojibake():
    report = build_after_market_report()
    gov_text = "\n".join(report["governance_notes"]["bullets"])
    _assert_no_mojibake(gov_text)
    md = render_markdown_report(report)
    section = md.split("## 6. Governance")[1] if "## 6. Governance" in md else md
    _assert_no_mojibake(section)


def test_build_after_market_report_has_all_sections():
    report = build_after_market_report()
    for section in REQUIRED_SECTIONS:
        assert section in report


def test_report_has_metric_status_view():
    view = build_after_market_report()["metric_status_view"]
    assert "metric_status_table" in view
    assert "missing_count" in view
    assert "missing_metrics" in view
    assert view["yellow_count"] >= 0
    assert "final escalation depends on rule confirmation" in view["explanation"]


def test_report_missing_metrics_not_presented_as_green():
    view = build_after_market_report()["metric_status_view"]
    for row in view["metric_status_table"]:
        if row["status"] == "missing":
            assert row["metric_available"] is False
    md = render_markdown_report(build_after_market_report())
    assert "Missing metrics:" in md
    assert "missing" in md.lower()


def test_rendered_markdown_includes_metric_status_summary():
    md = render_markdown_report(build_after_market_report())
    assert "### Metric Status Summary" in md


def test_render_markdown_includes_required_headings():
    report = build_after_market_report()
    md = render_markdown_report(report)
    for heading in MARKDOWN_HEADINGS:
        assert heading in md


def test_executive_escalation_matches_highest_alert():
    report = build_after_market_report()
    strat = report["strategy_alert_view"]
    alerts = strat.get("primary_actionable_alerts") or strat["triggered_alerts"]
    expected = "green"
    if alerts:
        levels = {str(a["escalation_level"]).lower() for a in alerts}
        if "red" in levels:
            expected = "red"
        elif "yellow" in levels:
            expected = "yellow"
    assert report["executive_risk_summary"]["overall_escalation_level"] == expected


def test_governance_notes_present():
    report = build_after_market_report()
    gov = report["governance_notes"]
    assert gov["no_live_api"] is True
    assert gov["no_execution"] is True
    assert "look-ahead" in gov["no_look_ahead"].lower() or "as_of_date" in gov["no_look_ahead"]


def test_markdown_forbidden_phrases_absent():
    md = render_markdown_report(build_after_market_report()).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in md


def test_market_close_snapshot_present():
    snap = build_after_market_report()["market_close_snapshot"]
    assert "VIX level" in snap
    assert "SPY return" in snap
    assert "HYG vs LQD relative return" in snap


def test_portfolio_risk_readout_present():
    readout = build_after_market_report()["portfolio_risk_readout"]
    assert "portfolio drawdown" in readout
    assert readout["exposure_by_asset_class"]
    assert readout["exposure_by_risk_bucket"]


def test_factor_risk_view_present():
    view = build_after_market_report()["factor_risk_view"]
    assert view["top_positive_factor_contributions"]
    assert "not a Barra" in view["interpretation"]


def test_strategy_alerts_from_rule_engine():
    report = build_after_market_report()
    assert "triggered_alerts" in report["strategy_alert_view"]
    for alert in report["strategy_alert_view"]["triggered_alerts"]:
        assert alert["escalation_level"] in ("yellow", "red")


def test_report_excludes_green_from_triggered_alerts():
    strat = build_after_market_report()["strategy_alert_view"]
    for alert in strat["triggered_alerts"]:
        assert alert["escalation_level"] != "green"


def test_report_informational_context_field():
    strat = build_after_market_report()["strategy_alert_view"]
    assert "informational_context_alerts" in strat
    assert "informational_context_mode" in strat
    assert "informational_context_note" in strat


def test_green_only_report_normal_context_mode(monkeypatch, tmp_path):
    import json

    from src.regime.rule_engine import (
        ALERT_COLUMNS,
        INFORMATIONAL_CONTEXT_MODE_NORMAL,
        derive_informational_context_note,
        run_rule_engine,
    )

    metrics = {
        "VIX level": 14.0,
        "VIX change": 1.0,
        "SPY return": 0.01,
        "QQQ return": 0.01,
        "IWM return": 0.01,
        "TLT return": 0.01,
        "HYG return": 0.01,
        "LQD return": 0.01,
        "GLD return": 0.01,
        "USO return": 0.005,
        "UUP return": 0.005,
        "HYG vs LQD relative return": 0.0,
        "SPY drawdown": -0.01,
        "portfolio drawdown": -0.01,
        "portfolio VaR": 0.5,
        "headline severity": 0,
        "cross-asset confirmation count": 0,
        "strategy return deviation": 0,
    }
    path = tmp_path / "green_ctx.json"
    path.write_text(
        json.dumps(
            {
                "as_of_date": "2026-04-14",
                "data_source": "test",
                "timestamp": "2026-04-14T00:00:00+00:00",
                "metrics": metrics,
            }
        ),
        encoding="utf-8",
    )
    engine = run_rule_engine(metrics_path=path)
    monkeypatch.setattr(
        "src.reporting.after_market_report._run_rule_engine_for_snapshot",
        lambda snapshot, config_dir=None: engine,
    )
    report = build_after_market_report(as_of_date="2026-04-14")
    strat = report["strategy_alert_view"]
    assert strat["informational_context_mode"] == INFORMATIONAL_CONTEXT_MODE_NORMAL
    assert "green informational context is active" in strat[
        "informational_context_note"
    ].lower()
    assert report["executive_risk_summary"]["overall_escalation_level"] == "green"
    assert strat["human_review_required_count"] == 0


def test_report_stress_context_with_informational(monkeypatch):
    import pandas as pd

    from src.regime.rule_engine import (
        INFORMATIONAL_CONTEXT_MODE_STRESS,
        INFORMATIONAL_STRESS_OVERRIDE_LABEL,
        RED_INFORMATIONAL_DISCLAIMER,
        derive_informational_context_mode,
        derive_informational_context_note,
    )

    def _row(rule_id: str, level: str) -> dict:
        return {
            "rule_id": rule_id,
            "regime_signal": "test",
            "risk_level": "high",
            "priority": 4,
            "escalation_level": level,
            "triggered_thresholds": "t1",
            "triggered_threshold_severities": "high",
            "affected_factors": "f1",
            "affected_strategies": "s1",
            "recommended_action": "monitor",
            "requires_human_review": level in ("yellow", "red"),
            "notes": "test",
        }

    actionable = pd.DataFrame([_row("credit_stress", "red")])
    informational = pd.DataFrame([_row("risk_on", "green")])
    mode = derive_informational_context_mode(actionable, informational)
    engine = {
        "alerts": actionable,
        "informational_alerts": informational,
        "informational_context_mode": mode,
        "informational_context_note": derive_informational_context_note(mode, True),
        "all_alerts": pd.concat([actionable, informational], ignore_index=True),
        "threshold_hits": pd.DataFrame(),
        "missing_metrics": [],
        "as_of_date": "2026-04-14",
        "data_source": "test",
        "timestamp": "2026-04-14T00:00:00+00:00",
    }
    monkeypatch.setattr(
        "src.reporting.after_market_report._run_rule_engine_for_snapshot",
        lambda snapshot, config_dir=None: engine,
    )
    report = build_after_market_report(as_of_date="2026-04-14")
    strat = report["strategy_alert_view"]
    assert strat["informational_context_mode"] == INFORMATIONAL_CONTEXT_MODE_STRESS
    assert INFORMATIONAL_STRESS_OVERRIDE_LABEL in strat["informational_context_note"]
    assert strat["informational_stress_disclaimer"] == RED_INFORMATIONAL_DISCLAIMER
    assert report["executive_risk_summary"]["overall_escalation_level"] == "red"
    assert strat["human_review_required_count"] == 1


def test_report_caution_context_yellow_and_informational(monkeypatch):
    import pandas as pd

    from src.regime.rule_engine import (
        INFORMATIONAL_CONTEXT_MODE_CAUTION,
        derive_informational_context_mode,
        derive_informational_context_note,
    )

    def _row(rule_id: str, level: str) -> dict:
        return {
            "rule_id": rule_id,
            "regime_signal": "test",
            "risk_level": "high",
            "priority": 4,
            "escalation_level": level,
            "triggered_thresholds": "t1",
            "triggered_threshold_severities": "high",
            "affected_factors": "f1",
            "affected_strategies": "s1",
            "recommended_action": "monitor",
            "requires_human_review": level in ("yellow", "red"),
            "notes": "test",
        }

    actionable = pd.DataFrame([_row("high_volatility", "yellow")])
    informational = pd.DataFrame([_row("credit_calm", "green")])
    mode = derive_informational_context_mode(actionable, informational)
    engine = {
        "alerts": actionable,
        "informational_alerts": informational,
        "informational_context_mode": mode,
        "informational_context_note": derive_informational_context_note(mode, True),
        "all_alerts": pd.concat([actionable, informational], ignore_index=True),
        "threshold_hits": pd.DataFrame(),
        "missing_metrics": [],
        "as_of_date": "2026-04-14",
        "data_source": "test",
        "timestamp": "2026-04-14T00:00:00+00:00",
    }
    monkeypatch.setattr(
        "src.reporting.after_market_report._run_rule_engine_for_snapshot",
        lambda snapshot, config_dir=None: engine,
    )
    report = build_after_market_report(as_of_date="2026-04-14")
    strat = report["strategy_alert_view"]
    assert strat["informational_context_mode"] == INFORMATIONAL_CONTEXT_MODE_CAUTION
    assert report["executive_risk_summary"]["overall_escalation_level"] == "yellow"
    assert strat["human_review_required_count"] == 1
    assert strat["informational_stress_disclaimer"] is None


def test_informational_never_affects_escalation_or_human_review():
    from src.data.config_loader import load_all_configs
    from src.regime.rule_engine import (
        aggregate_rule_alerts,
        evaluate_thresholds,
        split_actionable_and_informational_alerts,
    )
    from src.reporting.after_market_report import (
        _derive_overall_escalation,
        _human_review_count,
    )

    metrics = {
        "VIX level": 14.0,
        "VIX change": 1.0,
        "SPY return": 0.01,
        "HYG vs LQD relative return": 0.0,
        "UUP return": 0.005,
        "TIP return": 0.005,
        "QQQ return": 0.01,
        "IWM return": 0.01,
        "TLT return": 0.01,
        "HYG return": 0.01,
        "LQD return": 0.01,
        "GLD return": 0.01,
        "USO return": 0.005,
        "SPY drawdown": -0.01,
        "portfolio drawdown": -0.01,
        "portfolio VaR": 0.5,
        "headline severity": 0,
        "cross-asset confirmation count": 0,
        "strategy return deviation": 0,
    }
    configs = load_all_configs()
    hits, _ = evaluate_thresholds(metrics, configs["regime_thresholds"])
    all_alerts = aggregate_rule_alerts(hits, configs["regime_rules"])
    _, informational = split_actionable_and_informational_alerts(all_alerts)
    assert not informational.empty
    assert _derive_overall_escalation(informational) == "green"
    assert _human_review_count(informational) == 0


def test_human_review_counts_only_actionable():
    report = build_after_market_report()
    strat = report["strategy_alert_view"]
    primary = strat.get("primary_actionable_alerts", strat["triggered_alerts"])
    assert strat["human_review_required_count"] == len(
        [a for a in primary if a["requires_human_review"]]
    )


def test_report_caution_empty_informational_note(monkeypatch):
    import pandas as pd

    from src.regime.rule_engine import (
        INFORMATIONAL_CONTEXT_MODE_CAUTION,
        derive_informational_context_mode,
        derive_informational_context_note,
    )

    def _row(rule_id: str, level: str) -> dict:
        return {
            "rule_id": rule_id,
            "regime_signal": "test",
            "risk_level": "high",
            "priority": 4,
            "escalation_level": level,
            "triggered_thresholds": "t1",
            "triggered_threshold_severities": "high",
            "affected_factors": "f1",
            "affected_strategies": "s1",
            "recommended_action": "monitor",
            "requires_human_review": level in ("yellow", "red"),
            "notes": "test",
        }

    actionable = pd.DataFrame([_row("high_volatility", "yellow")])
    informational = pd.DataFrame(columns=[c for c in actionable.columns])
    mode = derive_informational_context_mode(actionable, informational)
    engine = {
        "alerts": actionable,
        "informational_alerts": informational,
        "informational_context_mode": mode,
        "informational_context_note": derive_informational_context_note(mode, False),
        "all_alerts": actionable.copy(),
        "threshold_hits": pd.DataFrame(),
        "missing_metrics": [],
        "as_of_date": "2026-04-14",
        "data_source": "test",
        "timestamp": "2026-04-14T00:00:00+00:00",
    }
    monkeypatch.setattr(
        "src.reporting.after_market_report._run_rule_engine_for_snapshot",
        lambda snapshot, config_dir=None: engine,
    )
    strat = build_after_market_report(as_of_date="2026-04-14")["strategy_alert_view"]
    assert strat["informational_context_mode"] == INFORMATIONAL_CONTEXT_MODE_CAUTION
    assert "no green informational context is displayed" in strat[
        "informational_context_note"
    ].lower()


def test_markdown_stress_disclaimer_when_red_and_informational(monkeypatch):
    import pandas as pd

    from src.regime.rule_engine import (
        derive_informational_context_mode,
        derive_informational_context_note,
    )

    def _row(rule_id: str, level: str) -> dict:
        return {
            "rule_id": rule_id,
            "regime_signal": "test",
            "risk_level": "high",
            "priority": 4,
            "escalation_level": level,
            "triggered_thresholds": "t1",
            "triggered_threshold_severities": "high",
            "affected_factors": "f1",
            "affected_strategies": "s1",
            "recommended_action": "monitor",
            "requires_human_review": level in ("yellow", "red"),
            "notes": "test",
        }

    actionable = pd.DataFrame([_row("credit_stress", "red")])
    informational = pd.DataFrame([_row("risk_on", "green")])
    mode = derive_informational_context_mode(actionable, informational)
    engine = {
        "alerts": actionable,
        "informational_alerts": informational,
        "informational_context_mode": mode,
        "informational_context_note": derive_informational_context_note(mode, True),
        "all_alerts": pd.concat([actionable, informational], ignore_index=True),
        "threshold_hits": pd.DataFrame(),
        "missing_metrics": [],
        "as_of_date": "2026-04-14",
        "data_source": "test",
        "timestamp": "2026-04-14T00:00:00+00:00",
    }
    monkeypatch.setattr(
        "src.reporting.after_market_report._run_rule_engine_for_snapshot",
        lambda snapshot, config_dir=None: engine,
    )
    md = render_markdown_report(build_after_market_report(as_of_date="2026-04-14"))
    assert "stress override" in md.lower()
    assert "not de-risking evidence" in md.lower()


def test_overall_escalation_green_when_only_informational(monkeypatch, tmp_path):
    import json

    from src.regime.rule_engine import run_rule_engine

    metrics = {
        "VIX level": 14.0,
        "VIX change": 1.0,
        "SPY return": 0.01,
        "QQQ return": 0.01,
        "IWM return": 0.01,
        "TLT return": 0.01,
        "HYG return": 0.01,
        "LQD return": 0.01,
        "GLD return": 0.01,
        "USO return": 0.005,
        "UUP return": 0.005,
        "HYG vs LQD relative return": 0.0,
        "SPY drawdown": -0.01,
        "portfolio drawdown": -0.01,
        "portfolio VaR": 0.5,
        "headline severity": 0,
        "cross-asset confirmation count": 0,
        "strategy return deviation": 0,
    }
    path = tmp_path / "green_only_report.json"
    path.write_text(
        json.dumps(
            {
                "as_of_date": "2026-04-14",
                "data_source": "test_green_only",
                "timestamp": "2026-04-14T00:00:00+00:00",
                "metrics": metrics,
            }
        ),
        encoding="utf-8",
    )
    engine = run_rule_engine(metrics_path=path)
    assert engine["alerts"].empty
    assert not engine["informational_alerts"].empty

    monkeypatch.setattr(
        "src.reporting.after_market_report._run_rule_engine_for_snapshot",
        lambda snapshot, config_dir=None: engine,
    )
    report = build_after_market_report(as_of_date="2026-04-14")
    assert report["executive_risk_summary"]["overall_escalation_level"] == "green"
    assert not report["strategy_alert_view"]["triggered_alerts"]
    assert report["strategy_alert_view"]["informational_context_alerts"]


def test_markdown_informational_context_section_when_present():
    md = render_markdown_report(build_after_market_report())
    if "### Informational context" in md:
        assert "not action triggers" in md.lower()


def test_next_day_watchlist_present():
    watch = build_after_market_report()["next_day_watchlist"]
    assert watch["risk_factors_to_monitor"]
    assert watch["human_approval_required_items"]


def test_write_after_market_report_to_temp_dir(tmp_path: Path):
    out = write_after_market_report(output_dir=tmp_path)
    assert out.suffix == ".md"
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("# After-Market Risk Report")


def test_computed_report_includes_yellow_high_volatility_alert():
    report = build_after_market_report()
    alerts = report["strategy_alert_view"]["triggered_alerts"]
    hv = [a for a in alerts if a["rule_id"] == "high_volatility"]
    assert len(hv) == 1
    assert hv[0]["escalation_level"] == "yellow"
    assert any(a["escalation_level"] == "yellow" for a in alerts)


def test_computed_report_overall_escalation_matches_highest_alert():
    report = build_after_market_report()
    alerts = report["strategy_alert_view"]["triggered_alerts"]
    levels = {a["escalation_level"] for a in alerts}
    expected = "green"
    if "red" in levels:
        expected = "red"
    elif "yellow" in levels:
        expected = "yellow"
    assert report["executive_risk_summary"]["overall_escalation_level"] == expected


def test_yellow_only_snapshot_overall_escalation_is_yellow(tmp_path):
    import json

    from src.portfolio.metrics_builder import snapshot_to_jsonable
    from src.regime.rule_engine import run_rule_engine
    from src.reporting.after_market_report import _derive_overall_escalation

    metrics = {
        "VIX level": 24.0,
        "VIX change": 3.5,
        "SPY return": -0.01,
        "QQQ return": 0.01,
        "IWM return": 0.01,
        "TLT return": 0.01,
        "HYG return": 0.01,
        "LQD return": 0.01,
        "GLD return": 0.01,
        "USO return": 0.01,
        "UUP return": 0.005,
        "HYG vs LQD relative return": -0.006,
        "SPY drawdown": -0.01,
        "portfolio drawdown": -0.01,
        "portfolio VaR": 0.5,
        "headline severity": 0,
        "cross-asset confirmation count": 0,
        "strategy return deviation": 0,
    }
    payload = {
        "as_of_date": "2026-04-14",
        "data_source": "test_yellow_only",
        "timestamp": "2026-04-14T00:00:00+00:00",
        "metrics": metrics,
    }
    path = tmp_path / "yellow_only.json"
    path.write_text(json.dumps(snapshot_to_jsonable(payload)), encoding="utf-8")

    alerts = run_rule_engine(metrics_path=path)["alerts"]
    assert len(alerts) == 1
    assert alerts.iloc[0]["rule_id"] == "high_volatility"
    assert alerts.iloc[0]["escalation_level"] == "yellow"
    assert _derive_overall_escalation(alerts) == "yellow"


def test_no_look_ahead_earlier_vs_final_date():
    early = build_after_market_report(as_of_date=EARLY_AS_OF)
    late = build_after_market_report(as_of_date=LATE_AS_OF)

    assert early["metadata"]["as_of_date"] == EARLY_AS_OF
    assert late["metadata"]["as_of_date"] == LATE_AS_OF

    early_spy = early["market_close_snapshot"]["SPY return"]["value"]
    late_spy = late["market_close_snapshot"]["SPY return"]["value"]
    assert early_spy != late_spy

    early_contrib = early["factor_risk_view"]["top_positive_factor_contributions"]
    late_contrib = late["factor_risk_view"]["top_positive_factor_contributions"]
    early_top = max(r["contribution_to_return"] for r in early_contrib)
    late_top = max(r["contribution_to_return"] for r in late_contrib)
    assert early_top != late_top or early_spy != late_spy

    assert early["metadata"]["as_of_date"] != late["metadata"]["as_of_date"]
