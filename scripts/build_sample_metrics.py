"""Build computed metrics snapshot from sample prices and run rule engine."""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.portfolio.metrics_builder import (
    DEFAULT_PRICE_PATH,
    build_metrics_snapshot,
    snapshot_to_jsonable,
)
from src.regime.rule_engine import run_rule_engine

OUTPUT_PATH = _ROOT / "data" / "samples" / "computed_metrics_snapshot.json"


def main() -> None:
    snapshot = build_metrics_snapshot(price_path=DEFAULT_PRICE_PATH)
    payload = snapshot_to_jsonable(snapshot)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"Wrote: {OUTPUT_PATH}")
    print(f"as_of_date: {payload['as_of_date']}")
    print(f"data_source: {payload['data_source']}")
    print(f"metrics_count: {len(payload['metrics'])}")

    result = run_rule_engine(metrics_path=OUTPUT_PATH)
    hits = result["threshold_hits"]
    fired = hits[hits["hit"] == True]  # noqa: E712
    actionable = result["alerts"]
    primary = result.get("primary_alerts", actionable)
    subsumed = result.get("subsumed_alerts", actionable.iloc[0:0])
    informational = result["informational_alerts"]

    print(f"threshold_hits: {len(fired)}")
    print(f"actionable rule_alerts: {len(actionable)}")
    print(f"primary_alerts: {len(primary)}")
    print(f"subsumed_alerts: {len(subsumed)}")
    print(f"informational_alerts: {len(informational)}")
    print(f"informational_context_mode: {result.get('informational_context_mode')}")
    print(f"informational_context_note: {result.get('informational_context_note')}")
    missing = result["missing_metrics"]
    print(f"missing_metrics: {', '.join(missing) if missing else '(none)'}")

    print("\nTop actionable alerts:")
    for _, row in actionable.head(5).iterrows():
        print(
            f"  - {row['rule_id']} | {row['escalation_level']} | {row['risk_level']} | "
            f"priority={row['priority']} | {row['recommended_action']}"
        )


if __name__ == "__main__":
    main()
