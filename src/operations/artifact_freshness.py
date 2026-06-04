"""Artifact freshness checks for OpenBB prototype dashboard display."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data.config_loader import PROJECT_ROOT

DEFAULT_PIPELINE_REPORT_PATH = PROJECT_ROOT / "output" / "openbb_daily_pipeline_run.json"

REQUIRED_ARTIFACT_KEYS = [
    "processed_price_path",
    "quality_report_path",
    "metrics_output_path",
    "market_monitor_output_path",
    "overnight_watchlist_output_path",
]


def evaluate_openbb_pipeline_freshness(
    pipeline_report_path: Path | str = DEFAULT_PIPELINE_REPORT_PATH,
) -> dict[str, Any]:
    """
    Check whether OpenBB display artifacts come from a successful pipeline run.

    This is a dashboard/display guard only. It does not alter official risk logic.
    """
    report_path = Path(pipeline_report_path)
    result: dict[str, Any] = {
        "pipeline_report_path": str(report_path),
        "report_exists": report_path.exists(),
        "is_fresh": False,
        "status": None,
        "generated_at_utc": None,
        "reason": None,
        "missing_artifacts": [],
        "artifact_paths": {},
        "summary": {},
    }

    if not report_path.exists():
        result["reason"] = "pipeline report missing; run python scripts/run_openbb_daily_pipeline.py"
        return result

    with report_path.open(encoding="utf-8") as handle:
        report = json.load(handle)

    result["status"] = report.get("status")
    result["generated_at_utc"] = report.get("generated_at_utc")
    result["summary"] = report.get("summary", {})
    result["official_risk_decision_allowed"] = report.get("official_risk_decision_allowed")

    if report.get("official_risk_decision_allowed") is True:
        result["reason"] = "pipeline report unexpectedly allows official risk decisions"
        return result

    if report.get("status") != "success":
        failed = next(
            (step for step in report.get("steps", []) if step.get("status") == "failed"),
            None,
        )
        failed_name = failed.get("name") if failed else "unknown"
        result["reason"] = f"latest pipeline status is failed at {failed_name}"
        return result

    missing: list[str] = []
    artifact_paths: dict[str, str] = {}
    for key in REQUIRED_ARTIFACT_KEYS:
        path_value = report.get(key)
        artifact_paths[key] = str(path_value) if path_value else ""
        if not path_value or not Path(path_value).exists():
            missing.append(key)

    result["artifact_paths"] = artifact_paths
    result["missing_artifacts"] = missing
    if missing:
        result["reason"] = f"latest successful pipeline is missing artifacts: {missing}"
        return result

    result["is_fresh"] = True
    result["reason"] = "latest pipeline succeeded and required artifacts exist"
    return result
