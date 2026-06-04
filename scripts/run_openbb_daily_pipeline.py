"""Run OpenBB prototype daily pipeline and write audit report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.operations.openbb_daily_pipeline import (
    DEFAULT_MARKET_MONITOR_PATH,
    DEFAULT_METRICS_PATH,
    DEFAULT_OVERNIGHT_WATCHLIST_PATH,
    DEFAULT_PROCESSED_PATH,
    DEFAULT_QUALITY_REPORT_PATH,
    DEFAULT_RAW_PATH,
    run_openbb_daily_pipeline,
)

DEFAULT_PIPELINE_REPORT_PATH = _ROOT / "output" / "openbb_daily_pipeline_run.json"


def main(
    raw_path: Path | None = None,
    processed_path: Path | None = None,
    quality_report_path: Path | None = None,
    metrics_path: Path | None = None,
    market_monitor_path: Path | None = None,
    overnight_watchlist_path: Path | None = None,
    pipeline_report_path: Path | None = None,
) -> dict:
    report = run_openbb_daily_pipeline(
        raw_price_path=raw_path or DEFAULT_RAW_PATH,
        processed_price_path=processed_path or DEFAULT_PROCESSED_PATH,
        quality_report_path=quality_report_path or DEFAULT_QUALITY_REPORT_PATH,
        metrics_output_path=metrics_path or DEFAULT_METRICS_PATH,
        market_monitor_output_path=market_monitor_path or DEFAULT_MARKET_MONITOR_PATH,
        overnight_watchlist_output_path=overnight_watchlist_path or DEFAULT_OVERNIGHT_WATCHLIST_PATH,
    )

    out_path = pipeline_report_path or DEFAULT_PIPELINE_REPORT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    summary = report["summary"]
    print(f"pipeline_report: {out_path}")
    print(f"status: {report['status']}")
    print(f"official_eod_usable: {summary.get('official_eod_usable')}")
    print(f"metrics_as_of_date: {summary.get('metrics_as_of_date')}")
    print(f"actionable_alert_count: {summary.get('actionable_alert_count')}")
    print(f"watchlist_count: {summary.get('watchlist_count')}")
    print(f"urgent_review_count: {summary.get('urgent_review_count')}")
    print("official_risk_decision_allowed: false")

    if report["status"] != "success":
        failed = next((s for s in report["steps"] if s["status"] == "failed"), None)
        if failed:
            print(f"failed_step: {failed['name']}")
            print(f"error: {failed.get('error')}")
        raise SystemExit(1)

    return report


if __name__ == "__main__":
    main()
