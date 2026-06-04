"""Generate after-market risk memo from latest official EOD prototype data."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.reporting.after_market_report import build_after_market_report, write_after_market_report
from src.operations.artifact_freshness import evaluate_openbb_pipeline_freshness

OPENBB_PIPELINE_REPORT = _ROOT / "output" / "openbb_daily_pipeline_run.json"
OPENBB_PROCESSED_PRICES = _ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"


def main() -> None:
    freshness = evaluate_openbb_pipeline_freshness(OPENBB_PIPELINE_REPORT)
    if freshness["is_fresh"] and OPENBB_PROCESSED_PRICES.exists():
        price_path = OPENBB_PROCESSED_PRICES
        expected_source = "openbb_yfinance"
        label = "openbb_yfinance_official_eod_prototype"
    else:
        price_path = None
        expected_source = "sample_synthetic"
        label = "sample_replay_fallback"

    out_path = write_after_market_report(
        price_path=price_path,
        expected_source=expected_source,
        sample_or_live_label=label,
    )
    as_of = out_path.stem.replace("after_market_risk_report_", "")
    report = build_after_market_report(
        as_of_date=as_of,
        price_path=price_path,
        expected_source=expected_source,
        sample_or_live_label=label,
    )
    exe = report["executive_risk_summary"]
    strat = report["strategy_alert_view"]
    alerts = strat["triggered_alerts"]

    print(f"output path: {out_path}")
    print(f"as_of_date: {report['metadata']['as_of_date']}")
    print(f"mode: {report['metadata']['sample_or_live_label']}")
    print(f"data_source: {report['metadata']['data_source']}")
    print(f"overall escalation: {exe['overall_escalation_level']}")
    print(f"alert count: {len(alerts)}")
    print(f"red alert count: {len(strat['red_alerts'])}")
    print(f"yellow alert count: {len(strat['yellow_alerts'])}")
    print(f"human-review-required alert count: {strat['human_review_required_count']}")


if __name__ == "__main__":
    main()
