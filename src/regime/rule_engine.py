"""
Prototype regime and risk rule engine (dry-run).

What: Evaluate mock or live daily metrics against regime_thresholds and regime_rules.
Why: Monitoring alerts and proposed actions only; no trade execution.
Inputs: JSON metrics snapshot; CSV configs via config_loader.
Outputs: Threshold hits, rule-level alerts, missing metric warnings.
Pitfalls: Escalation uses confirmation policy and threshold severity, not priority alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.config_loader import DEFAULT_CONFIG_DIR, PROJECT_ROOT, load_all_configs

DEFAULT_METRICS_PATH = PROJECT_ROOT / "data" / "samples" / "mock_daily_metrics.json"

RISK_LEVEL_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

THRESHOLD_HIT_COLUMNS = [
    "threshold_id",
    "linked_rule_id",
    "metric_name",
    "operator",
    "threshold_value",
    "metric_value",
    "severity",
    "notes",
    "hit",
]

ALERT_COLUMNS = [
    "rule_id",
    "regime_signal",
    "risk_level",
    "priority",
    "escalation_level",
    "triggered_thresholds",
    "triggered_threshold_severities",
    "affected_factors",
    "affected_strategies",
    "recommended_action",
    "requires_human_review",
    "notes",
]

ALERT_HIERARCHY_COLUMNS = ALERT_COLUMNS + [
    "is_subsumed",
    "subsumed_by",
    "display_group",
]

# Subsumed rule -> dominant rule when both are active in the same snapshot.
ALERT_SUBSUME_BY: dict[str, str] = {
    "credit_stress": "liquidity_stress",
}

ERM_ESCALATION_LEVELS = ("green", "yellow", "red")

INFORMATIONAL_CONTEXT_MODE_NORMAL = "normal_context"
INFORMATIONAL_CONTEXT_MODE_CAUTION = "caution_context"
INFORMATIONAL_CONTEXT_MODE_STRESS = "stress_context"

INFORMATIONAL_STRESS_OVERRIDE_LABEL = (
    "Benign context present but overridden by actionable stress alerts"
)

RED_INFORMATIONAL_DISCLAIMER = (
    "Green informational signals are not de-risking evidence and do not offset "
    "confirmed red/yellow alerts."
)

RULE_CONFIRMATION_POLICY: dict[str, dict[str, frozenset[str]]] = {
    "geopolitical_shock": {
        "required_all": frozenset(
            {"headline_severity_min", "cross_asset_confirm_min"}
        ),
    },
    "risk_on": {
        "required_all": frozenset({"risk_on_vix_max", "risk_on_spy_return_min"}),
        "blocked_any": frozenset(
            {
                "vix_elevated_min",
                "vix_high_min",
                "vix_change_1d_elevated",
                "risk_off_vix_min",
                "hyg_lqd_rel_20d_stress",
                "liquidity_hyg_lqd_stress",
            }
        ),
    },
    "risk_off": {
        "required_all": frozenset({"risk_off_vix_min"}),
        "required_any": frozenset(
            {"risk_off_spy_return_max", "spy_drawdown_60d"}
        ),
    },
    "low_volatility": {
        "required_all": frozenset({"vix_calm_max"}),
        "blocked_any": frozenset(
            {
                "vix_elevated_min",
                "vix_high_min",
                "vix_change_1d_elevated",
            }
        ),
    },
    "credit_stress": {
        "required_all": frozenset(
            {"hyg_lqd_rel_20d_stress", "credit_stress_vix_min"}
        ),
    },
    "credit_calm": {
        "required_all": frozenset({"hyg_lqd_rel_20d_calm"}),
        "blocked_any": frozenset(
            {
                "credit_stress_vix_min",
                "vix_elevated_min",
                "hyg_lqd_rel_20d_stress",
                "liquidity_hyg_lqd_stress",
            }
        ),
    },
    "liquidity_stress": {
        "required_all": frozenset(
            {"liquidity_hyg_lqd_stress", "vix_stress_liquidity"}
        ),
    },
    "inflation_pressure": {
        "required_all": frozenset({"tip_20d_return_up"}),
        "required_any": frozenset(
            {"inflation_uso_5d_support", "inflation_tlt_5d_down_support"}
        ),
    },
}

HARD_RED_RULES = frozenset(
    {"geopolitical_shock", "liquidity_stress", "var_breach", "drawdown_breach"}
)

GREEN_INFORMATIONAL_RULES = frozenset(
    {"low_volatility", "credit_calm", "risk_on"}
)

YELLOW_DEFAULT_RULES = frozenset(
    {
        "rates_up",
        "rates_down",
        "usd_pressure",
        "oil_shock",
        "strategy_drift",
    }
)

# risk_off-linked thresholds only; portfolio limit breaches are separate rules.
RISK_OFF_RED_UPGRADE_THRESHOLDS = frozenset({"spy_drawdown_60d"})

HIGH_VOLATILITY_RED_CONFIRM_ANY = frozenset(
    {
        "vix_change_1d_elevated",
        "risk_off_spy_return_max",
        "spy_drawdown_60d",
    }
)


def load_metrics_json(path: Path | str) -> dict[str, Any]:
    """Load daily metrics JSON with as_of_date, data_source, timestamp, and metrics."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Metrics file not found: {file_path}")
    with file_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    for key in ("as_of_date", "data_source", "metrics"):
        if key not in payload:
            raise ValueError(f"Metrics JSON missing required key: {key}")
    if not isinstance(payload["metrics"], dict):
        raise ValueError("Metrics JSON 'metrics' must be an object")
    return payload


def map_escalation_level(priority: int) -> str:
    """
    Legacy priority fallback mapping (not primary alert escalation logic).

    priority 1-2 -> green
    priority 3   -> yellow
    priority 4-5 -> red
    """
    p = int(priority)
    if p < 1 or p > 5:
        raise ValueError(f"priority must be between 1 and 5; got {priority}")
    if p <= 2:
        return "green"
    if p == 3:
        return "yellow"
    return "red"


def compare_metric(value: float, operator: str, threshold: float) -> bool:
    """Compare a numeric metric to a threshold using a supported operator."""
    ops = {
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }
    op = operator.strip()
    if op not in ops:
        raise ValueError(f"Unsupported operator: {operator}")
    return ops[op](float(value), float(threshold))


def evaluate_thresholds(
    metrics: dict[str, Any],
    thresholds_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Evaluate each threshold row against metrics.

    Returns threshold hits (all rows with hit flag) and missing metric names.
    Includes severity and notes from regime_thresholds.csv for escalation logic.
    """
    missing: list[str] = []
    rows: list[dict[str, Any]] = []

    for _, row in thresholds_df.iterrows():
        metric_name = str(row["metric_name"]).strip()
        threshold_id = str(row["threshold_id"])
        linked_rule_id = str(row["linked_rule_id"])
        operator = str(row["operator"]).strip()
        threshold_value = float(row["threshold_value"])
        severity = str(row["severity"]).strip()
        notes = str(row["notes"]).strip()

        base = {
            "threshold_id": threshold_id,
            "linked_rule_id": linked_rule_id,
            "metric_name": metric_name,
            "operator": operator,
            "threshold_value": threshold_value,
            "severity": severity,
            "notes": notes,
        }

        if metric_name not in metrics:
            if metric_name not in missing:
                missing.append(metric_name)
            rows.append({**base, "metric_value": None, "hit": False, "missing": True})
            continue

        raw_value = metrics[metric_name]
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            if metric_name not in missing:
                missing.append(metric_name)
            rows.append({**base, "metric_value": None, "hit": False, "missing": True})
            continue

        metric_value = float(raw_value)
        hit = compare_metric(metric_value, operator, threshold_value)
        rows.append({**base, "metric_value": metric_value, "hit": hit, "missing": False})

    hits_df = pd.DataFrame(rows)
    return hits_df, sorted(missing)


def rule_passes_confirmation_policy(
    rule_id: str,
    hit_threshold_ids: set[str],
    all_hit_threshold_ids: set[str] | None = None,
) -> bool:
    """
    Return True when rule-specific multi-threshold confirmation is satisfied.

    required_all: rule-linked hits that must all be present in hit_threshold_ids.
    required_any: at least one of these must be in hit_threshold_ids.
    blocked_any: if any of these fired anywhere in the snapshot, rule is suppressed.

    Rules without an entry fire on any linked threshold hit (OR at rule level).
    """
    policy = RULE_CONFIRMATION_POLICY.get(rule_id)
    if policy is None:
        return True

    global_hits = all_hit_threshold_ids if all_hit_threshold_ids is not None else hit_threshold_ids

    blocked_any = policy.get("blocked_any", frozenset())
    if blocked_any and (blocked_any & global_hits):
        return False

    required_all = policy.get("required_all", frozenset())
    if required_all and not required_all.issubset(hit_threshold_ids):
        return False

    required_any = policy.get("required_any", frozenset())
    if required_any and not (required_any & hit_threshold_ids):
        return False

    return True


def rule_passes_threshold_gate(
    rule_id: str,
    hit_threshold_ids: set[str],
    all_hit_threshold_ids: set[str] | None = None,
) -> bool:
    """Backward-compatible alias for confirmation policy checks."""
    return rule_passes_confirmation_policy(
        rule_id, hit_threshold_ids, all_hit_threshold_ids
    )


def derive_alert_escalation(
    rule_id: str,
    priority: int,
    hit_threshold_ids: set[str],
    hit_severities: set[str],
    all_hit_threshold_ids: set[str] | None = None,
) -> str:
    """
    Calibrate ERM escalation from threshold severities and rule-specific policy.

    RED: hard_limit_red, extreme_market_red (documented), or confirmed_regime_red.
    YELLOW: yellow_watch / defensive review candidates.
    GREEN: normal informational monitoring.
    """
    hits = {tid for tid in hit_threshold_ids if tid}
    severities = {str(s).strip().lower() for s in hit_severities if str(s).strip()}
    global_hits = (
        {tid for tid in all_hit_threshold_ids if tid}
        if all_hit_threshold_ids is not None
        else hits
    )

    if rule_id == "var_breach":
        if "portfolio_var_ratio" in hits:
            return "red"
        if "portfolio_var_ratio_watch" in hits:
            return "yellow"
        return "yellow"

    if rule_id == "drawdown_breach":
        if "portfolio_drawdown_limit" in hits:
            return "red"
        if "portfolio_drawdown_warning" in hits:
            return "yellow"
        return "yellow"

    if rule_id == "high_volatility":
        if "vix_high_min" in hits and (
            HIGH_VOLATILITY_RED_CONFIRM_ANY & global_hits
        ):
            return "red"
        if hits & frozenset(
            {"vix_elevated_min", "vix_change_1d_elevated", "vix_high_min"}
        ):
            return "yellow"
        return map_escalation_level(priority)

    if rule_id == "risk_off":
        if hits & RISK_OFF_RED_UPGRADE_THRESHOLDS:
            return "red"
        return "yellow"

    if rule_id == "credit_stress":
        return "red"

    if rule_id in GREEN_INFORMATIONAL_RULES:
        return "green"

    if rule_id in HARD_RED_RULES:
        if rule_id in {"geopolitical_shock", "liquidity_stress"}:
            return "red"
        if "critical" in severities:
            return "red"

    if rule_id == "inflation_pressure":
        return "yellow"

    if rule_id in YELLOW_DEFAULT_RULES:
        return "yellow"

    if "critical" in severities:
        return "red"

    priority_level = int(priority)
    if priority_level <= 2:
        return "green"
    if priority_level == 3:
        return "yellow"
    return "yellow"


def _apply_confirmation_policy(fired: pd.DataFrame) -> pd.DataFrame:
    """Drop rule hits that fail explicit multi-threshold confirmation."""
    if fired.empty:
        return fired
    all_hit_ids = set(fired["threshold_id"].astype(str))
    kept: list[pd.DataFrame] = []
    for rule_id, group in fired.groupby("linked_rule_id", sort=False):
        hit_ids = set(group["threshold_id"].astype(str))
        if rule_passes_confirmation_policy(str(rule_id), hit_ids, all_hit_ids):
            kept.append(group)
    if not kept:
        return fired.iloc[0:0].copy()
    return pd.concat(kept, ignore_index=True)


def aggregate_rule_alerts(
    threshold_hits_df: pd.DataFrame,
    regime_rules_df: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate threshold hits into rule-level alerts joined with regime_rules."""
    fired = threshold_hits_df[threshold_hits_df["hit"] == True].copy()  # noqa: E712
    fired = _apply_confirmation_policy(fired)
    if fired.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    grouped = (
        fired.groupby("linked_rule_id", as_index=False)
        .agg(
            triggered_thresholds=(
                "threshold_id",
                lambda s: ";".join(sorted(set(s.astype(str)))),
            ),
            triggered_threshold_severities=(
                "severity",
                lambda s: ";".join(sorted(set(s.astype(str)))),
            ),
        )
        .rename(columns={"linked_rule_id": "rule_id"})
    )

    alerts = grouped.merge(
        regime_rules_df,
        left_on="rule_id",
        right_on="rule_id",
        how="left",
    )

    if alerts["regime_signal"].isna().any():
        unknown = grouped.loc[alerts["regime_signal"].isna(), "rule_id"].tolist()
        raise ValueError(f"Threshold hits reference unknown rule_id values: {unknown}")

    alerts["priority"] = alerts["priority"].astype(int)
    all_hit_ids = set(fired["threshold_id"].astype(str))
    alerts["escalation_level"] = alerts.apply(
        lambda row: derive_alert_escalation(
            str(row["rule_id"]),
            int(row["priority"]),
            set(str(row["triggered_thresholds"]).split(";")),
            set(str(row["triggered_threshold_severities"]).split(";")),
            all_hit_ids,
        ),
        axis=1,
    )
    alerts["requires_human_review"] = alerts["escalation_level"].isin(
        ["red", "yellow"]
    )

    alerts["risk_level_rank"] = alerts["risk_level"].map(RISK_LEVEL_ORDER).fillna(99)
    alerts = alerts.sort_values(
        by=["priority", "risk_level_rank"],
        ascending=[False, True],
    ).drop(columns=["risk_level_rank"])

    return alerts[ALERT_COLUMNS]


def derive_informational_context_mode(
    actionable_alerts: pd.DataFrame,
    informational_alerts: pd.DataFrame | None = None,
) -> str:
    """
    Label how green informational context should be read alongside actionable alerts.

    informational_alerts is accepted for API symmetry; mode depends on actionable only.
    """
    _ = informational_alerts
    if actionable_alerts.empty:
        return INFORMATIONAL_CONTEXT_MODE_NORMAL
    levels = set(
        actionable_alerts["escalation_level"].astype(str).str.lower().tolist()
    )
    if "red" in levels:
        return INFORMATIONAL_CONTEXT_MODE_STRESS
    if "yellow" in levels:
        return INFORMATIONAL_CONTEXT_MODE_CAUTION
    return INFORMATIONAL_CONTEXT_MODE_NORMAL


def derive_informational_context_note(
    mode: str,
    has_informational_context: bool,
) -> str:
    """Human-readable note for report/dashboard informational sections."""
    if not has_informational_context:
        if mode == INFORMATIONAL_CONTEXT_MODE_STRESS:
            return (
                "Red/yellow actionable stress alerts are active; no green "
                "informational context is displayed."
            )
        if mode == INFORMATIONAL_CONTEXT_MODE_CAUTION:
            return (
                "Yellow actionable alerts are active; no green informational "
                "context is displayed."
            )
        return "No green informational rule context is active."

    if mode == INFORMATIONAL_CONTEXT_MODE_STRESS:
        return (
            f"{INFORMATIONAL_STRESS_OVERRIDE_LABEL}. "
            "Green context does not offset confirmed red/yellow actionable alerts."
        )
    if mode == INFORMATIONAL_CONTEXT_MODE_CAUTION:
        return (
            "Green informational context is visible alongside yellow actionable alerts. "
            "Benign signals do not reduce required review or escalation."
        )
    return (
        "Green informational context is active; no yellow/red actionable alerts "
        "are present."
    )


def get_informational_context_display(
    mode: str,
    has_informational_context: bool,
) -> dict[str, str]:
    """Title and caption for dashboard/report informational sections."""
    caption = derive_informational_context_note(mode, has_informational_context)
    if mode == INFORMATIONAL_CONTEXT_MODE_STRESS:
        return {
            "section_title": "Informational context (stress override)",
            "caption": caption,
            "tone": "warning",
        }
    if mode == INFORMATIONAL_CONTEXT_MODE_CAUTION:
        return {
            "section_title": "Informational context (caution)",
            "caption": caption,
            "tone": "caution",
        }
    return {
        "section_title": "Informational context",
        "caption": caption,
        "tone": "info",
    }


def subsumed_alert_explanation(subsumed_rule: str, dominator_rule: str) -> str:
    """Risk-manager wording for subsumed/context alerts in report and dashboard."""
    return (
        f"{subsumed_rule} is shown as context because {dominator_rule} is the "
        "dominant escalation."
    )


def apply_alert_hierarchy(
    actionable_alerts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Annotate actionable alerts with hierarchy metadata and split primary vs subsumed.

    Does not remove rules from the actionable table; audit evidence stays in alerts.
    """
    empty = pd.DataFrame(columns=ALERT_HIERARCHY_COLUMNS)
    if actionable_alerts.empty:
        return empty.copy(), empty.copy(), empty.copy()

    annotated = actionable_alerts.copy()
    active_rules = set(annotated["rule_id"].astype(str))
    annotated["is_subsumed"] = False
    annotated["subsumed_by"] = ""
    annotated["display_group"] = "primary"

    for subsumed_rule, dominator in ALERT_SUBSUME_BY.items():
        if subsumed_rule in active_rules and dominator in active_rules:
            mask = annotated["rule_id"].astype(str) == subsumed_rule
            annotated.loc[mask, "is_subsumed"] = True
            annotated.loc[mask, "subsumed_by"] = dominator
            annotated.loc[mask, "display_group"] = "subsumed_context"

    primary = annotated[~annotated["is_subsumed"]].copy()
    subsumed = annotated[annotated["is_subsumed"]].copy()
    return annotated, primary, subsumed


def escalation_basis_alerts(
    primary_alerts: pd.DataFrame,
    alerts: pd.DataFrame,
) -> pd.DataFrame:
    """Alerts used for overall escalation and human-review counts."""
    if primary_alerts is not None and not primary_alerts.empty:
        return primary_alerts
    return alerts


def split_actionable_and_informational_alerts(
    all_alerts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split aggregated alerts into actionable (yellow/red) and informational (green).

    Green informational rules are kept for context but must not drive escalation.
    """
    empty = pd.DataFrame(columns=ALERT_COLUMNS)
    if all_alerts.empty:
        return empty.copy(), empty.copy()
    levels = all_alerts["escalation_level"].astype(str).str.lower()
    actionable = all_alerts[levels.isin(["yellow", "red"])].copy()
    informational = all_alerts[levels == "green"].copy()
    return actionable, informational


def run_rule_engine(
    metrics_path: Path | str | None = None,
    config_dir: Path | str | None = None,
) -> dict[str, Any]:
    """
    Run full dry-run: load configs, metrics, evaluate, aggregate alerts.

    Returns dict with metadata, threshold_hits, alerts (yellow/red actionable only),
    informational_alerts (green context), all_alerts (full table), missing_metrics.
    """
    configs = load_all_configs(config_dir)
    metrics_payload = load_metrics_json(
        metrics_path or DEFAULT_METRICS_PATH
    )
    metrics = metrics_payload["metrics"]

    threshold_hits, missing_metrics = evaluate_thresholds(
        metrics,
        configs["regime_thresholds"],
    )
    all_alerts = aggregate_rule_alerts(
        threshold_hits,
        configs["regime_rules"],
    )
    alerts, informational_alerts = split_actionable_and_informational_alerts(
        all_alerts
    )
    alerts, primary_alerts, subsumed_alerts = apply_alert_hierarchy(alerts)
    basis = escalation_basis_alerts(primary_alerts, alerts)
    informational_context_mode = derive_informational_context_mode(
        basis, informational_alerts
    )
    has_informational_context = not informational_alerts.empty
    informational_context_note = derive_informational_context_note(
        informational_context_mode,
        has_informational_context,
    )

    return {
        "as_of_date": metrics_payload.get("as_of_date"),
        "data_source": metrics_payload.get("data_source"),
        "timestamp": metrics_payload.get("timestamp"),
        "threshold_hits": threshold_hits,
        "alerts": alerts,
        "primary_alerts": primary_alerts,
        "subsumed_alerts": subsumed_alerts,
        "informational_alerts": informational_alerts,
        "all_alerts": all_alerts,
        "informational_context_mode": informational_context_mode,
        "informational_context_note": informational_context_note,
        "missing_metrics": missing_metrics,
    }
