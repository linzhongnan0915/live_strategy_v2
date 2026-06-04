"""Tests for OpenBB pipeline artifact freshness guard."""

import json
from pathlib import Path

from src.operations.artifact_freshness import evaluate_openbb_pipeline_freshness


def _write_report(
    tmp_path: Path,
    status: str = "success",
    create_artifacts: bool = True,
) -> Path:
    artifact_paths = {
        "processed_price_path": tmp_path / "processed.csv",
        "quality_report_path": tmp_path / "quality.json",
        "metrics_output_path": tmp_path / "metrics.json",
        "market_monitor_output_path": tmp_path / "monitor.json",
        "overnight_watchlist_output_path": tmp_path / "watchlist.json",
    }
    if create_artifacts:
        for path in artifact_paths.values():
            path.write_text("{}", encoding="utf-8")

    report = {
        "generated_at_utc": "2026-06-02T20:00:00+00:00",
        "run_id": "2026-06-02T20:00:00+00:00",
        "status": status,
        "official_risk_decision_allowed": False,
        "summary": {"official_eod_usable": status == "success"},
        "steps": [
            {
                "name": "raw_input_check",
                "status": "failed" if status == "failed" else "success",
            }
        ],
    }
    report.update({key: str(path) for key, path in artifact_paths.items()})
    report_path = tmp_path / "pipeline_run.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


def test_missing_pipeline_report_not_fresh(tmp_path):
    result = evaluate_openbb_pipeline_freshness(tmp_path / "missing.json")
    assert result["is_fresh"] is False
    assert "pipeline report missing" in result["reason"]


def test_successful_pipeline_with_artifacts_is_fresh(tmp_path):
    report_path = _write_report(tmp_path)
    result = evaluate_openbb_pipeline_freshness(report_path)
    assert result["is_fresh"] is True
    assert result["missing_artifacts"] == []
    assert result["status"] == "success"


def test_failed_pipeline_not_fresh(tmp_path):
    report_path = _write_report(tmp_path, status="failed")
    result = evaluate_openbb_pipeline_freshness(report_path)
    assert result["is_fresh"] is False
    assert "failed" in result["reason"]


def test_missing_artifact_not_fresh(tmp_path):
    report_path = _write_report(tmp_path, create_artifacts=False)
    result = evaluate_openbb_pipeline_freshness(report_path)
    assert result["is_fresh"] is False
    assert "market_monitor_output_path" in result["missing_artifacts"]


def test_official_decision_allowed_report_not_fresh(tmp_path):
    report_path = _write_report(tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["official_risk_decision_allowed"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = evaluate_openbb_pipeline_freshness(report_path)
    assert result["is_fresh"] is False
    assert "official risk decisions" in result["reason"]
