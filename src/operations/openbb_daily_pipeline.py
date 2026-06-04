"""
OpenBB prototype daily pipeline orchestration (operations layer).

Runs process -> quality -> metrics -> market monitor -> overnight watchlist.
Does not fetch live data; does not alter official risk trigger logic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.config_loader import PROJECT_ROOT
from src.data.price_panel_quality import validate_official_eod_panel
from src.monitoring.live_market_snapshot import (
    build_market_monitor_snapshot,
    snapshot_to_jsonable as monitor_to_jsonable,
)
from src.monitoring.overnight_watchlist import build_overnight_watchlist
from src.portfolio.metrics_builder import (
    REQUIRED_PRICE_TICKERS,
    build_metrics_snapshot,
    snapshot_to_jsonable,
)
from src.regime.rule_engine import run_rule_engine
from scripts.check_openbb_data_quality import build_openbb_quality_report
from scripts.process_openbb_prices import align_openbb_price_history

DATA_MODE = "openbb_daily_pipeline_prototype"
OFFICIAL_EOD_SOURCE = "openbb_yfinance"

DEFAULT_RAW_PATH = PROJECT_ROOT / "data" / "raw" / "openbb_price_history.csv"
DEFAULT_PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
DEFAULT_QUALITY_REPORT_PATH = PROJECT_ROOT / "output" / "openbb_data_quality_report.json"
DEFAULT_METRICS_PATH = PROJECT_ROOT / "output" / "openbb_metrics_snapshot.json"
DEFAULT_MARKET_MONITOR_PATH = PROJECT_ROOT / "output" / "openbb_market_monitor_snapshot.json"
DEFAULT_OVERNIGHT_WATCHLIST_PATH = PROJECT_ROOT / "output" / "openbb_overnight_watchlist.json"


def _step_record(
    name: str,
    status: str,
    message: str,
    artifact_path: Path | str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "artifact_path": str(artifact_path) if artifact_path else None,
        "message": message,
        "error": error,
    }


def run_openbb_daily_pipeline(
    raw_price_path: Path | str,
    processed_price_path: Path | str,
    quality_report_path: Path | str,
    metrics_output_path: Path | str,
    market_monitor_output_path: Path | str,
    overnight_watchlist_output_path: Path | str,
) -> dict[str, Any]:
    """
    Execute OpenBB daily workflow in governance order.

    Stops on first failure. Does not fetch from OpenBB.
    """
    raw_p = Path(raw_price_path)
    proc_p = Path(processed_price_path)
    quality_p = Path(quality_report_path)
    metrics_p = Path(metrics_output_path)
    monitor_p = Path(market_monitor_output_path)
    watch_p = Path(overnight_watchlist_output_path)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "run_id": generated_at,
        "status": "failed",
        "data_mode": DATA_MODE,
        "official_risk_decision_allowed": False,
        "raw_price_path": str(raw_p),
        "processed_price_path": str(proc_p),
        "quality_report_path": str(quality_p),
        "metrics_output_path": str(metrics_p),
        "market_monitor_output_path": str(monitor_p),
        "overnight_watchlist_output_path": str(watch_p),
        "steps": [],
        "summary": {
            "official_eod_usable": False,
            "metrics_as_of_date": None,
            "metrics_data_source": None,
            "actionable_alert_count": 0,
            "primary_alert_count": 0,
            "informational_alert_count": 0,
            "watchlist_count": 0,
            "urgent_review_count": 0,
        },
    }

    def fail(step: dict[str, Any]) -> dict[str, Any]:
        result["steps"].append(step)
        return result

    if not raw_p.exists():
        return fail(
            _step_record(
                "raw_input_check",
                "failed",
                "raw OpenBB price file missing",
                error=(
                    f"raw file not found: {raw_p}. "
                    "Run python scripts/fetch_openbb_prices.py first."
                ),
            )
        )

    try:
        raw_df = pd.read_csv(raw_p)
        aligned, stats = align_openbb_price_history(raw_df)
        proc_p.parent.mkdir(parents=True, exist_ok=True)
        aligned.to_csv(proc_p, index=False)
        result["steps"].append(
            _step_record(
                "process_openbb_prices",
                "success",
                (
                    f"aligned {stats['processed_date_count']} dates; "
                    f"dropped {stats['dropped_incomplete_date_count']} incomplete dates"
                ),
                proc_p,
            )
        )
    except Exception as exc:
        return fail(
            _step_record(
                "process_openbb_prices",
                "failed",
                "failed to align raw OpenBB prices",
                proc_p,
                str(exc),
            )
        )

    try:
        quality_report = build_openbb_quality_report(
            raw_path=raw_p,
            processed_path=proc_p,
        )
        quality_p.parent.mkdir(parents=True, exist_ok=True)
        with quality_p.open("w", encoding="utf-8") as handle:
            json.dump(quality_report, handle, indent=2)
        official_usable = bool(quality_report.get("official_eod_usable"))
        result["summary"]["official_eod_usable"] = official_usable
        if not official_usable:
            err = (
                quality_report.get("processed", {}).get("validation_error")
                or "processed panel is not official_eod_ready"
            )
            return fail(
                _step_record(
                    "check_openbb_data_quality",
                    "failed",
                    "official EOD panel not usable",
                    quality_p,
                    str(err),
                )
            )
        result["steps"].append(
            _step_record(
                "check_openbb_data_quality",
                "success",
                "official_eod_usable=true",
                quality_p,
            )
        )
    except Exception as exc:
        return fail(
            _step_record(
                "check_openbb_data_quality",
                "failed",
                "data quality check failed",
                quality_p,
                str(exc),
            )
        )

    try:
        price_df = pd.read_csv(proc_p)
        validate_official_eod_panel(
            price_df,
            REQUIRED_PRICE_TICKERS,
            OFFICIAL_EOD_SOURCE,
        )
        snapshot = build_metrics_snapshot(
            price_path=proc_p,
            expected_source=OFFICIAL_EOD_SOURCE,
        )
        payload = snapshot_to_jsonable(snapshot)
        metrics_p.parent.mkdir(parents=True, exist_ok=True)
        with metrics_p.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        engine = run_rule_engine(metrics_path=metrics_p)
        actionable = engine["alerts"]
        primary = engine.get("primary_alerts", actionable)
        informational = engine["informational_alerts"]
        result["summary"]["metrics_as_of_date"] = payload.get("as_of_date")
        result["summary"]["metrics_data_source"] = payload.get("data_source")
        result["summary"]["actionable_alert_count"] = len(actionable)
        result["summary"]["primary_alert_count"] = len(primary)
        result["summary"]["informational_alert_count"] = len(informational)
        result["steps"].append(
            _step_record(
                "build_openbb_metrics",
                "success",
                (
                    f"metrics as_of_date={payload.get('as_of_date')}; "
                    f"actionable_alerts={len(actionable)}"
                ),
                metrics_p,
            )
        )
    except Exception as exc:
        return fail(
            _step_record(
                "build_openbb_metrics",
                "failed",
                "official EOD metrics build failed",
                metrics_p,
                str(exc),
            )
        )

    try:
        monitor = build_market_monitor_snapshot(
            raw_price_path=raw_p,
            processed_price_path=proc_p,
        )
        monitor_payload = monitor_to_jsonable(monitor)
        monitor_p.parent.mkdir(parents=True, exist_ok=True)
        with monitor_p.open("w", encoding="utf-8") as handle:
            json.dump(monitor_payload, handle, indent=2)
        result["steps"].append(
            _step_record(
                "build_market_monitor_snapshot",
                "success",
                f"market monitor ticker_count={monitor_payload.get('ticker_count')}",
                monitor_p,
            )
        )
    except Exception as exc:
        return fail(
            _step_record(
                "build_market_monitor_snapshot",
                "failed",
                "market monitor snapshot failed",
                monitor_p,
                str(exc),
            )
        )

    try:
        watchlist = build_overnight_watchlist(monitor_p)
        watch_p.parent.mkdir(parents=True, exist_ok=True)
        with watch_p.open("w", encoding="utf-8") as handle:
            json.dump(watchlist, handle, indent=2)
        urgent_count = sum(
            1 for item in watchlist["items"] if item.get("watch_level") == "urgent_review"
        )
        result["summary"]["watchlist_count"] = watchlist["summary"]["watchlist_count"]
        result["summary"]["urgent_review_count"] = urgent_count
        result["steps"].append(
            _step_record(
                "build_overnight_watchlist",
                "success",
                f"watchlist_count={watchlist['summary']['watchlist_count']}",
                watch_p,
            )
        )
    except Exception as exc:
        return fail(
            _step_record(
                "build_overnight_watchlist",
                "failed",
                "overnight watchlist build failed",
                watch_p,
                str(exc),
            )
        )

    result["status"] = "success"
    return result
