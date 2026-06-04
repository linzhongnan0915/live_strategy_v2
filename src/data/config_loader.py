"""
Load and validate live_strategy CSV configuration files.

What: Read holdings, strategy library, regime rules, regime thresholds, and factor mapping.
Why: Centralize config integrity checks before monitoring or backtest code runs.
Inputs: Optional paths or config_dir under project data/config/.
Outputs: pandas DataFrames; load_all_configs returns a dict of ten frames.
Pitfalls: Thresholds are prototype values; validation does not prove economic correctness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "data" / "config"

WEIGHT_SUM_TOLERANCE = 1e-6
ALLOWED_OPERATORS = {">", ">=", "<", "<=", "==", "!="}

HOLDINGS_COLUMNS = [
    "ticker",
    "name",
    "target_weight",
    "asset_class",
    "sector",
    "risk_bucket",
    "role",
    "notes",
]

STRATEGY_LIBRARY_COLUMNS = [
    "strategy_id",
    "strategy_name",
    "category",
    "objective",
    "target_etfs",
    "primary_factor",
    "secondary_factor",
    "valid_regime",
    "invalid_regime",
    "core_signal",
    "target_tilt",
    "risk_controls",
    "rebalance_frequency",
    "required_backtest",
    "failure_mode",
    "dashboard_action_label",
    "human_review_required",
]

ETF_UNIVERSE_COLUMNS = [
    "ticker",
    "name",
    "asset_class",
    "sector",
    "risk_bucket",
    "primary_factor",
    "secondary_factor",
    "liquidity_tier",
    "implementation_role",
    "notes",
]

STRATEGY_SCORING_POLICY_COLUMNS = [
    "score_component",
    "weight",
    "description",
]

REGIME_RULES_COLUMNS = [
    "rule_id",
    "regime_signal",
    "condition_description",
    "risk_level",
    "priority",
    "affected_factors",
    "affected_strategies",
    "recommended_action",
    "action_severity",
    "requires_human_review",
    "data_inputs",
    "notes",
]

REGIME_THRESHOLDS_COLUMNS = [
    "threshold_id",
    "linked_rule_id",
    "metric_name",
    "operator",
    "threshold_value",
    "lookback_window",
    "unit",
    "severity",
    "notes",
]

FACTOR_MAPPING_COLUMNS = [
    "factor_id",
    "factor_name",
    "proxy_ticker",
    "factor_group",
    "interpretation",
    "notes",
]

METRIC_STATUS_POLICY_COLUMNS = [
    "policy_id",
    "metric_name",
    "status",
    "operator",
    "threshold_value",
    "unit",
    "interpretation",
    "related_rules",
    "display_order",
    "notes",
]

ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
ALLOWED_METRIC_STATUS_BANDS = {"yellow", "red"}

ENVIRONMENT_STATES_COLUMNS = [
    "environment_id",
    "environment_name",
    "description",
    "primary_metrics",
    "confirmation_logic",
    "escalation_meaning",
    "de_escalation_conditions",
    "review_actions",
    "not_allowed",
]

ALERT_HIERARCHY_COLUMNS = [
    "environment_state",
    "dominant_rule_id",
    "subsumed_rule_id",
    "priority_rank",
    "relationship_type",
    "rationale",
    "dashboard_label",
    "active_by_default",
]

HARD_LIMIT_RULE_IDS = frozenset({"var_breach", "drawdown_breach"})
ALLOWED_HIERARCHY_RELATIONSHIP_TYPES = frozenset({"dominates", "context_only"})

REQUIRED_ENVIRONMENT_IDS = frozenset(
    {
        "normal_risk_on",
        "volatility_stress",
        "risk_off_equity_stress",
        "credit_stress",
        "liquidity_crisis",
        "rates_inflation_shock",
        "geopolitical_event_shock",
        "stabilization_re_risk_review",
    }
)


def _resolve_config_dir(config_dir: Path | str | None) -> Path:
    if config_dir is None:
        return DEFAULT_CONFIG_DIR
    return Path(config_dir)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return pd.read_csv(path)


def _require_columns(df: pd.DataFrame, columns: list[str], label: str) -> None:
    if list(df.columns) != columns:
        raise ValueError(
            f"{label} columns must be exactly {columns}; got {list(df.columns)}"
        )


def _require_non_empty(df: pd.DataFrame, fields: Iterable[str], label: str) -> None:
    for field in fields:
        if field not in df.columns:
            raise ValueError(f"{label} missing column: {field}")
        empty = df[field].isna() | (df[field].astype(str).str.strip() == "")
        if empty.any():
            bad = df.loc[empty, field].index.tolist()
            raise ValueError(f"{label} has empty values in '{field}' at rows {bad}")


def _parse_bool_series(series: pd.Series, label: str) -> pd.Series:
    normalized = series.astype(str).str.strip().str.upper()
    mapping = {"TRUE": True, "FALSE": False}
    if not normalized.isin(mapping).all():
        bad = normalized[~normalized.isin(mapping)].unique().tolist()
        raise ValueError(f"{label} human_review flags must be TRUE/FALSE; got {bad}")
    return normalized.map(mapping)


def load_holdings(path: Path | str | None = None) -> pd.DataFrame:
    """Load holdings.csv and validate."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "holdings.csv"
    df = _read_csv(file_path)
    validate_holdings(df)
    return df


def load_strategy_library(path: Path | str | None = None) -> pd.DataFrame:
    """Load strategy_library.csv and validate."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "strategy_library.csv"
    df = _read_csv(file_path)
    validate_strategy_library(df)
    return df


def load_etf_universe(path: Path | str | None = None) -> pd.DataFrame:
    """Load etf_universe.csv and validate."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "etf_universe.csv"
    df = _read_csv(file_path)
    validate_etf_universe(df)
    return df


def load_strategy_scoring_policy(path: Path | str | None = None) -> pd.DataFrame:
    """Load strategy_scoring_policy.csv and validate."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "strategy_scoring_policy.csv"
    df = _read_csv(file_path)
    validate_strategy_scoring_policy(df)
    return df


def load_regime_rules(path: Path | str | None = None) -> pd.DataFrame:
    """Load regime_rules.csv and validate against strategy library IDs."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "regime_rules.csv"
    df = _read_csv(file_path)
    strategies = load_strategy_library()
    strategy_ids = set(strategies["strategy_id"].astype(str))
    validate_regime_rules(df, strategy_ids)
    return df


def load_alert_hierarchy(
    path: Path | str | None = None,
    environment_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> pd.DataFrame:
    """Load alert_hierarchy.csv regime-aware dominance rules (config only; not runtime)."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "alert_hierarchy.csv"
    df = _read_csv(file_path)
    if environment_ids is None:
        environment_ids = set(load_environment_states()["environment_id"].astype(str))
    if rule_ids is None:
        rule_ids = set(load_regime_rules()["rule_id"].astype(str))
    validate_alert_hierarchy(df, environment_ids, rule_ids)
    return df


def load_environment_states(path: Path | str | None = None) -> pd.DataFrame:
    """Load environment_states.csv design skeleton (not wired to rule_engine)."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "environment_states.csv"
    df = _read_csv(file_path)
    validate_environment_states(df)
    return df


def load_metric_status_policy(path: Path | str | None = None) -> pd.DataFrame:
    """Load metric_status_policy.csv for dashboard metric-level status bands."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "metric_status_policy.csv"
    df = _read_csv(file_path)
    validate_metric_status_policy(df)
    return df


def load_factor_mapping(path: Path | str | None = None) -> pd.DataFrame:
    """Load factor_mapping.csv and validate observable proxy factor schema."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "factor_mapping.csv"
    df = _read_csv(file_path)
    validate_factor_mapping(df)
    return df


def load_regime_thresholds(
    path: Path | str | None = None,
    rule_ids: set[str] | None = None,
) -> pd.DataFrame:
    """Load regime_thresholds.csv and validate linked rules."""
    file_path = Path(path) if path else DEFAULT_CONFIG_DIR / "regime_thresholds.csv"
    df = _read_csv(file_path)
    if rule_ids is None:
        rules = load_regime_rules()
        rule_ids = set(rules["rule_id"].astype(str))
    validate_regime_thresholds(df, rule_ids)
    return df


def validate_holdings(df: pd.DataFrame) -> None:
    """Validate holdings schema and target_weight sum."""
    _require_columns(df, HOLDINGS_COLUMNS, "holdings")
    _require_non_empty(
        df,
        ["ticker", "asset_class", "risk_bucket", "role"],
        "holdings",
    )
    weights = pd.to_numeric(df["target_weight"], errors="coerce")
    if weights.isna().any():
        raise ValueError("holdings target_weight must be numeric")
    total = float(weights.sum())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(f"holdings target_weight must sum to 1.00; got {total:.6f}")


def validate_etf_universe(df: pd.DataFrame) -> None:
    """Validate ETF universe schema."""
    _require_columns(df, ETF_UNIVERSE_COLUMNS, "etf_universe")
    _require_non_empty(df, ["ticker", "name", "primary_factor"], "etf_universe")
    if df["ticker"].duplicated().any():
        raise ValueError("etf_universe ticker must be unique")


def validate_strategy_scoring_policy(df: pd.DataFrame) -> None:
    """Validate strategy scoring policy weights sum to 1."""
    _require_columns(df, STRATEGY_SCORING_POLICY_COLUMNS, "strategy_scoring_policy")
    weights = df["weight"].astype(float)
    total = float(weights.sum())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(f"strategy_scoring_policy weights must sum to 1.00; got {total:.6f}")


def validate_strategy_library(df: pd.DataFrame) -> None:
    """Validate strategy library schema and governance flags."""
    _require_columns(df, STRATEGY_LIBRARY_COLUMNS, "strategy_library")
    _require_non_empty(
        df,
        [
            "strategy_id",
            "strategy_name",
            "category",
            "target_etfs",
            "primary_factor",
            "valid_regime",
            "core_signal",
            "target_tilt",
            "risk_controls",
        ],
        "strategy_library",
    )
    if df["strategy_id"].duplicated().any():
        dupes = df.loc[df["strategy_id"].duplicated(), "strategy_id"].tolist()
        raise ValueError(f"strategy_library strategy_id must be unique; duplicates: {dupes}")
    review = _parse_bool_series(df["human_review_required"], "strategy_library")
    if not review.all():
        bad = df.loc[~review, "strategy_id"].tolist()
        raise ValueError(
            f"strategy_library human_review_required must be TRUE for all strategies; failed: {bad}"
        )


def validate_regime_rules(df: pd.DataFrame, strategy_ids: set[str]) -> None:
    """Validate regime rules schema, priorities, and strategy references."""
    _require_columns(df, REGIME_RULES_COLUMNS, "regime_rules")
    _require_non_empty(
        df,
        [
            "rule_id",
            "regime_signal",
            "condition_description",
            "risk_level",
            "priority",
            "recommended_action",
            "data_inputs",
        ],
        "regime_rules",
    )
    if df["rule_id"].duplicated().any():
        dupes = df.loc[df["rule_id"].duplicated(), "rule_id"].tolist()
        raise ValueError(f"regime_rules rule_id must be unique; duplicates: {dupes}")

    risk_levels = set(df["risk_level"].astype(str).str.strip())
    if not risk_levels.issubset(ALLOWED_RISK_LEVELS):
        bad = risk_levels - ALLOWED_RISK_LEVELS
        raise ValueError(f"regime_rules invalid risk_level values: {sorted(bad)}")

    priorities = pd.to_numeric(df["priority"], errors="coerce")
    if priorities.isna().any() or ((priorities < 1) | (priorities > 5)).any():
        raise ValueError("regime_rules priority must be integers from 1 to 5")
    if not priorities.astype(int).equals(priorities):
        raise ValueError("regime_rules priority must be whole numbers")

    review = _parse_bool_series(df["requires_human_review"], "regime_rules")
    high_priority = priorities >= 3
    if (high_priority & ~review).any():
        bad = df.loc[high_priority & ~review, "rule_id"].tolist()
        raise ValueError(
            f"regime_rules priority >= 3 requires human review TRUE; failed: {bad}"
        )

    for _, row in df.iterrows():
        strategies = [
            part.strip()
            for part in str(row["affected_strategies"]).split(";")
            if part.strip()
        ]
        unknown = [sid for sid in strategies if sid not in strategy_ids]
        if unknown:
            raise ValueError(
                f"regime_rules rule '{row['rule_id']}' references unknown strategies: {unknown}"
            )


def validate_regime_thresholds(df: pd.DataFrame, rule_ids: set[str]) -> None:
    """Validate regime thresholds schema, operators, and linked rules."""
    _require_columns(df, REGIME_THRESHOLDS_COLUMNS, "regime_thresholds")
    _require_non_empty(
        df,
        [
            "threshold_id",
            "linked_rule_id",
            "metric_name",
            "operator",
            "unit",
        ],
        "regime_thresholds",
    )

    if df["threshold_id"].duplicated().any():
        dupes = df.loc[df["threshold_id"].duplicated(), "threshold_id"].tolist()
        raise ValueError(f"regime_thresholds threshold_id must be unique; duplicates: {dupes}")

    linked = set(df["linked_rule_id"].astype(str).str.strip())
    unknown_rules = linked - rule_ids
    if unknown_rules:
        raise ValueError(
            f"regime_thresholds linked_rule_id must exist in regime_rules; unknown: {sorted(unknown_rules)}"
        )

    operators = set(df["operator"].astype(str).str.strip())
    bad_ops = operators - ALLOWED_OPERATORS
    if bad_ops:
        raise ValueError(
            f"regime_thresholds operator must be one of {sorted(ALLOWED_OPERATORS)}; got {sorted(bad_ops)}"
        )

    pd.to_numeric(df["threshold_value"], errors="raise")
    pd.to_numeric(df["lookback_window"], errors="raise")


def validate_environment_states(df: pd.DataFrame) -> None:
    """Validate environment state design skeleton schema."""
    _require_columns(df, ENVIRONMENT_STATES_COLUMNS, "environment_states")
    if df.empty:
        raise ValueError("environment_states is empty")
    _require_non_empty(
        df,
        ["environment_id", "environment_name", "description"],
        "environment_states",
    )
    if df["environment_id"].duplicated().any():
        dupes = df.loc[df["environment_id"].duplicated(), "environment_id"].tolist()
        raise ValueError(f"environment_states environment_id must be unique; duplicates: {dupes}")
    present = set(df["environment_id"].astype(str).str.strip())
    missing = REQUIRED_ENVIRONMENT_IDS - present
    if missing:
        raise ValueError(f"environment_states missing required ids: {sorted(missing)}")
    extra = present - REQUIRED_ENVIRONMENT_IDS
    if extra:
        raise ValueError(f"environment_states unknown ids: {sorted(extra)}")


def validate_metric_status_policy(df: pd.DataFrame) -> None:
    """Validate metric status policy schema for prototype display bands."""
    _require_columns(df, METRIC_STATUS_POLICY_COLUMNS, "metric_status_policy")
    if df.empty:
        raise ValueError("metric_status_policy is empty")
    _require_non_empty(
        df,
        ["policy_id", "metric_name", "status", "operator", "unit", "interpretation"],
        "metric_status_policy",
    )
    if df["policy_id"].duplicated().any():
        dupes = df.loc[df["policy_id"].duplicated(), "policy_id"].tolist()
        raise ValueError(f"metric_status_policy policy_id must be unique; duplicates: {dupes}")

    statuses = set(df["status"].astype(str).str.strip().str.lower())
    bad_status = statuses - ALLOWED_METRIC_STATUS_BANDS
    if bad_status:
        raise ValueError(
            f"metric_status_policy status must be yellow or red; got {sorted(bad_status)}"
        )

    operators = set(df["operator"].astype(str).str.strip())
    bad_ops = operators - ALLOWED_OPERATORS
    if bad_ops:
        raise ValueError(
            f"metric_status_policy operator must be one of {sorted(ALLOWED_OPERATORS)}; "
            f"got {sorted(bad_ops)}"
        )

    pd.to_numeric(df["threshold_value"], errors="raise")
    pd.to_numeric(df["display_order"], errors="raise")


def validate_alert_hierarchy(
    df: pd.DataFrame,
    environment_ids: set[str],
    rule_ids: set[str],
) -> None:
    """Validate regime-aware alert hierarchy config (design layer; not wired to engine)."""
    _require_columns(df, ALERT_HIERARCHY_COLUMNS, "alert_hierarchy")
    if df.empty:
        raise ValueError("alert_hierarchy is empty")
    _require_non_empty(
        df,
        [
            "environment_state",
            "dominant_rule_id",
            "subsumed_rule_id",
            "relationship_type",
            "rationale",
            "dashboard_label",
        ],
        "alert_hierarchy",
    )

    envs = set(df["environment_state"].astype(str).str.strip())
    unknown_env = envs - environment_ids
    if unknown_env:
        raise ValueError(
            f"alert_hierarchy environment_state must exist in environment_states; "
            f"unknown: {sorted(unknown_env)}"
        )

    dominants = set(df["dominant_rule_id"].astype(str).str.strip())
    subsumed = set(df["subsumed_rule_id"].astype(str).str.strip())
    unknown_rules = (dominants | subsumed) - rule_ids
    if unknown_rules:
        raise ValueError(
            f"alert_hierarchy rule ids must exist in regime_rules; unknown: {sorted(unknown_rules)}"
        )

    ranks = pd.to_numeric(df["priority_rank"], errors="coerce")
    if ranks.isna().any() or (ranks < 1).any() or not ranks.astype(int).equals(ranks):
        raise ValueError("alert_hierarchy priority_rank must be positive integers")

    _parse_bool_series(df["active_by_default"], "alert_hierarchy")

    rel_types = set(df["relationship_type"].astype(str).str.strip().str.lower())
    bad_rel = rel_types - ALLOWED_HIERARCHY_RELATIONSHIP_TYPES
    if bad_rel:
        raise ValueError(
            f"alert_hierarchy relationship_type invalid: {sorted(bad_rel)}; "
            f"allowed: {sorted(ALLOWED_HIERARCHY_RELATIONSHIP_TYPES)}"
        )

    if (df["dominant_rule_id"].astype(str) == df["subsumed_rule_id"].astype(str)).any():
        bad = df.loc[
            df["dominant_rule_id"].astype(str) == df["subsumed_rule_id"].astype(str),
            ["environment_state", "dominant_rule_id"],
        ]
        raise ValueError(f"alert_hierarchy cannot self-subsume: {bad.to_dict('records')}")

    hard_subsumed = subsumed & HARD_LIMIT_RULE_IDS
    if hard_subsumed:
        raise ValueError(
            f"alert_hierarchy must not subsume hard-limit rules: {sorted(hard_subsumed)}"
        )

    keys = df[["environment_state", "dominant_rule_id", "subsumed_rule_id"]].astype(str)
    if keys.duplicated().any():
        dupes = keys[keys.duplicated(keep=False)]
        raise ValueError(f"alert_hierarchy duplicate rows: {dupes.to_dict('records')}")


def validate_factor_mapping(df: pd.DataFrame) -> None:
    """Validate observable ETF proxy factor mapping schema."""
    _require_columns(df, FACTOR_MAPPING_COLUMNS, "factor_mapping")
    if len(df) < 1:
        raise ValueError("factor_mapping must contain at least one row")
    _require_non_empty(df, FACTOR_MAPPING_COLUMNS, "factor_mapping")
    if df["factor_id"].duplicated().any():
        dupes = df.loc[df["factor_id"].duplicated(), "factor_id"].tolist()
        raise ValueError(f"factor_mapping factor_id must be unique; duplicates: {dupes}")


def load_all_configs(config_dir: Path | str | None = None) -> dict[str, pd.DataFrame]:
    """
    Load and validate all config CSVs.

    Returns dict with keys: holdings, strategy_library, etf_universe,
    strategy_scoring_policy, regime_rules, regime_thresholds, factor_mapping,
    metric_status_policy, environment_states, alert_hierarchy.
    """
    base = _resolve_config_dir(config_dir)
    holdings = _read_csv(base / "holdings.csv")
    validate_holdings(holdings)

    strategy_library = _read_csv(base / "strategy_library.csv")
    validate_strategy_library(strategy_library)
    strategy_ids = set(strategy_library["strategy_id"].astype(str))

    etf_universe = _read_csv(base / "etf_universe.csv")
    validate_etf_universe(etf_universe)

    strategy_scoring_policy = _read_csv(base / "strategy_scoring_policy.csv")
    validate_strategy_scoring_policy(strategy_scoring_policy)

    regime_rules = _read_csv(base / "regime_rules.csv")
    validate_regime_rules(regime_rules, strategy_ids)
    rule_ids = set(regime_rules["rule_id"].astype(str))

    regime_thresholds = _read_csv(base / "regime_thresholds.csv")
    validate_regime_thresholds(regime_thresholds, rule_ids)

    factor_mapping = _read_csv(base / "factor_mapping.csv")
    validate_factor_mapping(factor_mapping)

    metric_status_policy = _read_csv(base / "metric_status_policy.csv")
    validate_metric_status_policy(metric_status_policy)

    environment_states = _read_csv(base / "environment_states.csv")
    validate_environment_states(environment_states)
    environment_ids = set(environment_states["environment_id"].astype(str))

    alert_hierarchy = _read_csv(base / "alert_hierarchy.csv")
    validate_alert_hierarchy(alert_hierarchy, environment_ids, rule_ids)

    return {
        "holdings": holdings,
        "strategy_library": strategy_library,
        "etf_universe": etf_universe,
        "strategy_scoring_policy": strategy_scoring_policy,
        "regime_rules": regime_rules,
        "regime_thresholds": regime_thresholds,
        "factor_mapping": factor_mapping,
        "metric_status_policy": metric_status_policy,
        "environment_states": environment_states,
        "alert_hierarchy": alert_hierarchy,
    }
