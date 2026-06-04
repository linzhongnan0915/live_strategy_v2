"""Build metrics snapshot from OpenBB raw prices and run rule engine (dry-run)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.data.price_panel_quality import validate_official_eod_panel
from src.portfolio.metrics_builder import (
    REQUIRED_PRICE_TICKERS,
    build_metrics_snapshot,
    snapshot_to_jsonable,
)
from src.regime.rule_engine import run_rule_engine

DEFAULT_INPUT_PATH = _ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
DEFAULT_OUTPUT_PATH = _ROOT / "output" / "openbb_metrics_snapshot.json"
OFFICIAL_EOD_SOURCE = "openbb_yfinance"
MISSING_INPUT_MESSAGE = (
    "Run python scripts/fetch_openbb_prices.py, then "
    "python scripts/process_openbb_prices.py first"
)


def main(
    input_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    in_path = input_path or DEFAULT_INPUT_PATH
    out_path = output_path or DEFAULT_OUTPUT_PATH

    if not in_path.exists():
        print(MISSING_INPUT_MESSAGE)
        raise SystemExit(1)

    price_df = pd.read_csv(in_path)
    try:
        validate_official_eod_panel(
            price_df,
            REQUIRED_PRICE_TICKERS,
            OFFICIAL_EOD_SOURCE,
        )
    except ValueError as exc:
        print("official_eod_quality_gate: fail")
        print(f"reason: {exc}")
        print("Run python scripts/check_openbb_data_quality.py for details")
        raise SystemExit(1) from exc

    print("official_eod_quality_gate: pass")
    snapshot = build_metrics_snapshot(
        price_path=in_path,
        expected_source=OFFICIAL_EOD_SOURCE,
    )
    payload = snapshot_to_jsonable(snapshot)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"input: {in_path}")
    print(f"output: {out_path}")
    print(f"as_of_date: {payload['as_of_date']}")
    print(f"data_source: {payload['data_source']}")
    print(f"metric_count: {len(payload['metrics'])}")

    result = run_rule_engine(metrics_path=out_path)
    hits = result["threshold_hits"]
    fired = hits[hits["hit"] == True]  # noqa: E712
    actionable = result["alerts"]
    primary = result.get("primary_alerts", actionable)
    subsumed = result.get("subsumed_alerts", actionable.iloc[0:0])
    informational = result["informational_alerts"]

    print(f"threshold_hits: {len(fired)}")
    print(f"actionable_alerts: {len(actionable)}")
    print(f"primary_alerts: {len(primary)}")
    print(f"subsumed_alerts: {len(subsumed)}")
    print(f"informational_alerts: {len(informational)}")
    missing = result["missing_metrics"]
    print(f"missing_metrics: {', '.join(missing) if missing else '(none)'}")

    print("\nTop primary alerts:")
    for _, row in primary.head(5).iterrows():
        print(
            f"  - {row['rule_id']} | {row['escalation_level']} | {row['risk_level']} | "
            f"priority={row['priority']} | {row['recommended_action']}"
        )


if __name__ == "__main__":
    main()
