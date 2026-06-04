"""
Metric-level status bands for dashboard and reporting (prototype).

What: Map individual metrics to green/yellow/red display status from metric_status_policy.csv.
Why: Show where pressure is building before rule-level confirmation and final escalation.
Inputs: Daily metrics dict and optional policy DataFrame from config_loader.
Outputs: Per-metric status table and summary counts (not rule alerts).
Pitfalls: Metric color is not final ERM escalation; missing data is not green.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.data.config_loader import load_metric_status_policy
from src.regime.rule_engine import compare_metric

STATUS_RANK = {"green": 0, "yellow": 1, "red": 2}
MISSING_STATUS = "missing"

METRIC_STATUS_COLUMNS = [
    "metric_name",
    "metric_value",
    "status",
    "triggered_policy_id",
    "operator",
    "threshold_value",
    "interpretation",
    "related_rules",
    "notes",
    "metric_available",
]


def _pick_worst_status(current: str, candidate: str) -> str:
    if STATUS_RANK[candidate] > STATUS_RANK[current]:
        return candidate
    return current


def _missing_row(metric_name: str, subset: pd.DataFrame, reason: str) -> dict[str, Any]:
    return {
        "metric_name": metric_name,
        "metric_value": None,
        "status": MISSING_STATUS,
        "triggered_policy_id": "",
        "operator": "",
        "threshold_value": None,
        "interpretation": reason,
        "related_rules": str(subset.iloc[0]["related_rules"]),
        "notes": "metric_unavailable",
        "metric_available": False,
    }


def derive_metric_statuses(
    metrics: dict[str, Any],
    policy_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Evaluate metric-level status from policy bands.

    Missing or empty policy metrics use status 'missing', not green.
    """
    policy = policy_df if policy_df is not None else load_metric_status_policy()
    policy_metrics = sorted(policy["metric_name"].astype(str).unique())
    rows: list[dict[str, Any]] = []

    for metric_name in policy_metrics:
        subset = policy[policy["metric_name"].astype(str) == metric_name].sort_values(
            "display_order"
        )
        if metric_name not in metrics:
            rows.append(
                _missing_row(
                    metric_name,
                    subset,
                    "Metric missing from snapshot; data-quality warning.",
                )
            )
            continue

        raw_value = metrics[metric_name]
        if raw_value is None or (isinstance(raw_value, str) and str(raw_value).strip() == ""):
            rows.append(
                _missing_row(
                    metric_name,
                    subset,
                    "Metric value empty; data-quality warning.",
                )
            )
            continue

        metric_value = float(raw_value)
        status = "green"
        triggered_policy_id = ""
        operator = ""
        threshold_value = None
        interpretation = "Within prototype normal band."
        related_rules = str(subset.iloc[0]["related_rules"])
        notes = str(subset.iloc[0]["notes"])

        for _, prow in subset.iterrows():
            op = str(prow["operator"]).strip()
            thresh = float(prow["threshold_value"])
            if compare_metric(metric_value, op, thresh):
                candidate = str(prow["status"]).strip().lower()
                if STATUS_RANK[candidate] >= STATUS_RANK[status]:
                    status = _pick_worst_status(status, candidate)
                    triggered_policy_id = str(prow["policy_id"])
                    operator = op
                    threshold_value = thresh
                    interpretation = str(prow["interpretation"])
                    related_rules = str(prow["related_rules"])
                    notes = str(prow["notes"])

        rows.append(
            {
                "metric_name": metric_name,
                "metric_value": metric_value,
                "status": status,
                "triggered_policy_id": triggered_policy_id,
                "operator": operator,
                "threshold_value": threshold_value,
                "interpretation": interpretation,
                "related_rules": related_rules,
                "notes": notes,
                "metric_available": True,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=METRIC_STATUS_COLUMNS)
    return df[METRIC_STATUS_COLUMNS]


def get_metric_status_summary(metric_status_df: pd.DataFrame) -> dict[str, Any]:
    """Summarize metric-level status counts; missing metrics are not counted as green."""
    missing_mask = metric_status_df["status"] == MISSING_STATUS
    missing_metrics = metric_status_df.loc[missing_mask, "metric_name"].tolist()
    available = metric_status_df[~missing_mask & metric_status_df["metric_available"]]

    if available.empty:
        return {
            "green_count": 0,
            "yellow_count": 0,
            "red_count": 0,
            "missing_count": int(missing_mask.sum()),
            "missing_metrics": missing_metrics,
            "yellow_metrics": [],
            "red_metrics": [],
            "green_metrics": [],
        }

    counts = available["status"].value_counts()
    return {
        "green_count": int(counts.get("green", 0)),
        "yellow_count": int(counts.get("yellow", 0)),
        "red_count": int(counts.get("red", 0)),
        "missing_count": int(missing_mask.sum()),
        "missing_metrics": missing_metrics,
        "yellow_metrics": available.loc[
            available["status"] == "yellow", "metric_name"
        ].tolist(),
        "red_metrics": available.loc[available["status"] == "red", "metric_name"].tolist(),
        "green_metrics": available.loc[
            available["status"] == "green", "metric_name"
        ].tolist(),
    }
