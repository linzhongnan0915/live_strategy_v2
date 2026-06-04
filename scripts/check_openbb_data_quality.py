"""Check OpenBB raw and processed price panel quality; write governance report."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.data.price_panel_quality import (
    READINESS_OFFICIAL_EOD,
    classify_panel_readiness,
    summarize_price_panel,
    validate_official_eod_panel,
)
from src.portfolio.metrics_builder import REQUIRED_PRICE_TICKERS

DEFAULT_RAW_PATH = _ROOT / "data" / "raw" / "openbb_price_history.csv"
DEFAULT_PROCESSED_PATH = _ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
DEFAULT_REPORT_PATH = _ROOT / "output" / "openbb_data_quality_report.json"
OFFICIAL_EOD_SOURCE = "openbb_yfinance"


def build_openbb_quality_report(
    raw_path: Path | None = None,
    processed_path: Path | None = None,
    required_tickers: list[str] | None = None,
    expected_source: str = OFFICIAL_EOD_SOURCE,
) -> dict[str, Any]:
    """Build JSON-serializable quality report for raw and processed panels."""
    tickers = list(required_tickers or REQUIRED_PRICE_TICKERS)
    raw_p = raw_path or DEFAULT_RAW_PATH
    proc_p = processed_path or DEFAULT_PROCESSED_PATH
    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "required_ticker_count": len(tickers),
        "raw": {"path": str(raw_p), "exists": raw_p.exists()},
        "processed": {"path": str(proc_p), "exists": proc_p.exists()},
        "official_eod_usable": False,
    }

    if raw_p.exists():
        raw_df = pd.read_csv(raw_p)
        raw_summary = summarize_price_panel(raw_df, tickers)
        report["raw"].update(
            {
                "summary": raw_summary,
                "readiness": classify_panel_readiness(raw_summary),
            }
        )
    else:
        report["raw"]["status"] = "missing"

    if proc_p.exists():
        proc_df = pd.read_csv(proc_p)
        proc_summary = summarize_price_panel(proc_df, tickers)
        proc_readiness = classify_panel_readiness(proc_summary)
        validation_error: str | None = None
        try:
            validate_official_eod_panel(proc_df, tickers, expected_source)
            validation_ok = True
        except ValueError as exc:
            validation_ok = False
            validation_error = str(exc)
        report["processed"].update(
            {
                "summary": proc_summary,
                "readiness": proc_readiness,
                "official_validation_ok": validation_ok,
                "validation_error": validation_error,
            }
        )
        report["official_eod_usable"] = (
            proc_readiness == READINESS_OFFICIAL_EOD and validation_ok
        )
    else:
        report["processed"]["status"] = "missing"

    return report


def main(
    raw_path: Path | None = None,
    processed_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    report = build_openbb_quality_report(raw_path, processed_path)
    out_path = report_path or DEFAULT_REPORT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    raw = report["raw"]
    proc = report["processed"]
    print(f"report: {out_path}")
    print(f"raw_path: {raw['path']} exists={raw['exists']}")
    if raw["exists"]:
        print(f"raw_readiness: {raw.get('readiness')}")
        rs = raw.get("summary", {})
        print(f"raw_incomplete_dates: {rs.get('incomplete_date_count', 0)}")
        print(f"raw_missing_tickers: {rs.get('missing_required_tickers', [])}")
        print(f"raw_duplicate_count: {rs.get('duplicate_date_ticker_count', 0)}")
    else:
        print("raw_readiness: missing")

    print(f"processed_path: {proc['path']} exists={proc['exists']}")
    if proc["exists"]:
        print(f"processed_readiness: {proc.get('readiness')}")
        ps = proc.get("summary", {})
        print(f"processed_incomplete_dates: {ps.get('incomplete_date_count', 0)}")
        print(f"processed_missing_tickers: {ps.get('missing_required_tickers', [])}")
        print(f"processed_duplicate_count: {ps.get('duplicate_date_ticker_count', 0)}")
        print(f"processed_validation_ok: {proc.get('official_validation_ok')}")
    else:
        print("processed_readiness: missing")

    usable = "yes" if report["official_eod_usable"] else "no"
    print(f"official_eod_usable: {usable}")
    return report


if __name__ == "__main__":
    main()
