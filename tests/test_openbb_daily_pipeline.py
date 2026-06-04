"""Tests for OpenBB daily pipeline runner (no network, no fetch)."""

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.operations.openbb_daily_pipeline import run_openbb_daily_pipeline
from src.portfolio.metrics_builder import DEFAULT_PRICE_PATH

ROOT = Path(__file__).resolve().parents[1]


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw": tmp_path / "raw.csv",
        "processed": tmp_path / "processed.csv",
        "quality": tmp_path / "quality.json",
        "metrics": tmp_path / "metrics.json",
        "monitor": tmp_path / "monitor.json",
        "watchlist": tmp_path / "watchlist.json",
    }


def _openbb_raw_df() -> pd.DataFrame:
    df = pd.read_csv(DEFAULT_PRICE_PATH)
    df["source"] = "openbb_yfinance"
    return df


def test_successful_pipeline_creates_artifacts(tmp_path):
    paths = _paths(tmp_path)
    _openbb_raw_df().to_csv(paths["raw"], index=False)

    report = run_openbb_daily_pipeline(
        paths["raw"],
        paths["processed"],
        paths["quality"],
        paths["metrics"],
        paths["monitor"],
        paths["watchlist"],
    )

    assert report["status"] == "success"
    assert paths["processed"].exists()
    assert paths["quality"].exists()
    assert paths["metrics"].exists()
    assert paths["monitor"].exists()
    assert paths["watchlist"].exists()
    assert report["summary"]["official_eod_usable"] is True
    assert report["summary"]["metrics_as_of_date"] is not None
    assert report["official_risk_decision_allowed"] is False


def test_missing_raw_fails_before_downstream(tmp_path):
    paths = _paths(tmp_path)
    report = run_openbb_daily_pipeline(
        paths["raw"],
        paths["processed"],
        paths["quality"],
        paths["metrics"],
        paths["monitor"],
        paths["watchlist"],
    )
    assert report["status"] == "failed"
    assert report["steps"][0]["name"] == "raw_input_check"
    assert not paths["processed"].exists()
    assert not paths["metrics"].exists()


def test_incomplete_raw_processed_quality_passes(tmp_path):
    paths = _paths(tmp_path)
    raw = _openbb_raw_df()
    last = raw["date"].max()
    partial = raw[raw["date"] == last].head(1).copy()
    partial["date"] = "2099-12-31"
    partial["ticker"] = "VIX"
    raw = pd.concat([raw, partial], ignore_index=True)
    raw.to_csv(paths["raw"], index=False)

    report = run_openbb_daily_pipeline(
        paths["raw"],
        paths["processed"],
        paths["quality"],
        paths["metrics"],
        paths["monitor"],
        paths["watchlist"],
    )
    assert report["status"] == "success"
    assert report["summary"]["official_eod_usable"] is True


def test_quality_failure_stops_before_metrics(tmp_path):
    paths = _paths(tmp_path)
    _openbb_raw_df().to_csv(paths["raw"], index=False)
    fake_quality = {
        "official_eod_usable": False,
        "processed": {"validation_error": "not ready"},
    }

    with patch(
        "src.operations.openbb_daily_pipeline.build_openbb_quality_report",
        return_value=fake_quality,
    ):
        report = run_openbb_daily_pipeline(
            paths["raw"],
            paths["processed"],
            paths["quality"],
            paths["metrics"],
            paths["monitor"],
            paths["watchlist"],
        )

    assert report["status"] == "failed"
    assert report["steps"][-1]["name"] == "check_openbb_data_quality"
    assert not paths["metrics"].exists()


def test_summary_contains_alert_and_watchlist_counts(tmp_path):
    paths = _paths(tmp_path)
    _openbb_raw_df().to_csv(paths["raw"], index=False)
    report = run_openbb_daily_pipeline(
        paths["raw"],
        paths["processed"],
        paths["quality"],
        paths["metrics"],
        paths["monitor"],
        paths["watchlist"],
    )
    assert "actionable_alert_count" in report["summary"]
    assert "watchlist_count" in report["summary"]


def test_failed_pipeline_writes_status_failed(tmp_path):
    from scripts.run_openbb_daily_pipeline import main

    paths = _paths(tmp_path)
    report_path = tmp_path / "pipeline_run.json"
    with pytest.raises(SystemExit) as exc:
        main(
            raw_path=paths["raw"],
            processed_path=paths["processed"],
            quality_report_path=paths["quality"],
            metrics_path=paths["metrics"],
            market_monitor_path=paths["monitor"],
            overnight_watchlist_path=paths["watchlist"],
            pipeline_report_path=report_path,
        )
    assert exc.value.code == 1
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["status"] == "failed"
    assert loaded["official_risk_decision_allowed"] is False
