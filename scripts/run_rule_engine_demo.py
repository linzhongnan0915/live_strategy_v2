"""Dry-run demo for prototype regime rule engine."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.regime.rule_engine import DEFAULT_METRICS_PATH, run_rule_engine


def main() -> None:
    result = run_rule_engine(metrics_path=DEFAULT_METRICS_PATH)
    actionable = result["alerts"]
    primary = result.get("primary_alerts", actionable)
    subsumed = result.get("subsumed_alerts", actionable.iloc[0:0])
    informational = result["informational_alerts"]
    hits = result["threshold_hits"]
    fired = hits[hits["hit"] == True]  # noqa: E712

    print(f"as_of_date: {result['as_of_date']}")
    print(f"data_source: {result['data_source']}")
    print(f"threshold_hits: {len(fired)}")
    print(f"actionable rule_alerts: {len(actionable)}")
    print(f"primary_alerts: {len(primary)}")
    print(f"subsumed_alerts: {len(subsumed)}")
    print(f"informational_alerts: {len(informational)}")
    print(f"informational_context_mode: {result.get('informational_context_mode')}")
    print(f"informational_context_note: {result.get('informational_context_note')}")
    if result["missing_metrics"]:
        print(f"missing_metrics: {', '.join(result['missing_metrics'])}")

    print("\nTop actionable alerts:")
    if actionable.empty:
        print("  (none)")
    else:
        for _, row in actionable.head(5).iterrows():
            print(
                f"  - {row['rule_id']} | {row['escalation_level']} | {row['risk_level']} | "
                f"priority={row['priority']} | {row['recommended_action']}"
            )

    if not informational.empty:
        print("\nInformational context rule ids:")
        for rule_id in informational["rule_id"].astype(str).tolist():
            print(f"  - {rule_id}")


if __name__ == "__main__":
    main()
