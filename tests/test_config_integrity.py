"""Config integrity tests for live_strategy CSV policy layer."""

import pandas as pd
import pytest

from src.data.config_loader import (
    ALERT_HIERARCHY_COLUMNS,
    ALLOWED_OPERATORS,
    DEFAULT_CONFIG_DIR,
    FACTOR_MAPPING_COLUMNS,
    HARD_LIMIT_RULE_IDS,
    load_alert_hierarchy,
    load_all_configs,
    load_factor_mapping,
    load_etf_universe,
    load_holdings,
    load_regime_rules,
    load_regime_thresholds,
    load_strategy_scoring_policy,
    load_strategy_library,
    validate_regime_thresholds,
)


def test_all_configs_load():
    configs = load_all_configs()
    assert set(configs) == {
        "holdings",
        "strategy_library",
        "etf_universe",
        "strategy_scoring_policy",
        "regime_rules",
        "regime_thresholds",
        "factor_mapping",
        "metric_status_policy",
        "environment_states",
        "alert_hierarchy",
    }
    for frame in configs.values():
        assert not frame.empty


def test_holdings_row_count_and_weight_sum():
    df = load_holdings()
    assert len(df) >= 35
    assert abs(df["target_weight"].astype(float).sum() - 1.0) < 1e-6
    assert {"XLK", "XLF", "XLE", "XLV", "XLP", "EFA", "EEM", "GLD"}.issubset(
        set(df["ticker"].astype(str))
    )
    universe = set(load_etf_universe()["ticker"].astype(str))
    assert set(df["ticker"].astype(str)).issubset(universe)
    assert "VIX" not in set(df["ticker"].astype(str))
    assert "VXX" not in set(df["ticker"].astype(str))


def test_strategy_library_row_count_and_human_review():
    df = load_strategy_library()
    assert len(df) >= 20
    assert (df["human_review_required"].astype(str).str.upper() == "TRUE").all()


def test_etf_universe_and_strategy_scoring_policy():
    universe = load_etf_universe()
    assert len(universe) >= 40
    assert universe["ticker"].nunique() == len(universe)
    assert {"SPY", "XLK", "XLF", "GLD", "VIX"}.issubset(
        set(universe["ticker"].astype(str))
    )

    policy = load_strategy_scoring_policy()
    assert abs(policy["weight"].astype(float).sum() - 1.0) < 1e-6


def test_regime_rules_row_count_and_strategy_references():
    strategies = load_strategy_library()
    strategy_ids = set(strategies["strategy_id"].astype(str))
    rules = load_regime_rules()
    assert len(rules) == 16

    for _, row in rules.iterrows():
        parts = [
            p.strip()
            for p in str(row["affected_strategies"]).split(";")
            if p.strip()
        ]
        assert all(part in strategy_ids for part in parts)

    priorities = rules["priority"].astype(int)
    review = rules["requires_human_review"].astype(str).str.upper() == "TRUE"
    assert (review | (priorities < 3)).all()
    assert review[priorities >= 3].all()


def test_regime_thresholds_linked_rules_exist():
    rules = load_regime_rules()
    rule_ids = set(rules["rule_id"].astype(str))
    thresholds = load_regime_thresholds(rule_ids=rule_ids)
    assert not thresholds.empty
    assert set(thresholds["linked_rule_id"].astype(str)).issubset(rule_ids)


def test_invalid_operator_fails_validation():
    rules = load_regime_rules()
    rule_ids = set(rules["rule_id"].astype(str))
    thresholds = load_regime_thresholds(rule_ids=rule_ids).copy()
    thresholds.loc[0, "operator"] = ">>"
    with pytest.raises(ValueError, match="operator"):
        validate_regime_thresholds(thresholds, rule_ids)


def test_factor_mapping_loads_and_schema():
    df = load_factor_mapping()
    assert not df.empty
    assert list(df.columns) == FACTOR_MAPPING_COLUMNS
    assert df["factor_id"].nunique() == len(df)
    assert (df["proxy_ticker"].astype(str).str.strip() != "").all()


def test_environment_states_schema_and_required_ids():
    from src.data.config_loader import (
        ENVIRONMENT_STATES_COLUMNS,
        REQUIRED_ENVIRONMENT_IDS,
        load_environment_states,
    )

    df = load_environment_states()
    assert list(df.columns) == ENVIRONMENT_STATES_COLUMNS
    assert set(df["environment_id"].astype(str)) == set(REQUIRED_ENVIRONMENT_IDS)
    assert (df["environment_id"].astype(str).str.strip() != "").all()
    assert (df["environment_name"].astype(str).str.strip() != "").all()


def test_alert_hierarchy_schema_and_references():
    from src.data.config_loader import REQUIRED_ENVIRONMENT_IDS, load_environment_states

    df = load_alert_hierarchy()
    assert list(df.columns) == ALERT_HIERARCHY_COLUMNS
    rules = load_regime_rules()
    rule_ids = set(rules["rule_id"].astype(str))
    env_ids = set(load_environment_states()["environment_id"].astype(str))
    assert env_ids == set(REQUIRED_ENVIRONMENT_IDS)
    assert set(df["environment_state"].astype(str)).issubset(env_ids)
    assert set(df["dominant_rule_id"].astype(str)).issubset(rule_ids)
    assert set(df["subsumed_rule_id"].astype(str)).issubset(rule_ids)
    assert not (set(df["subsumed_rule_id"].astype(str)) & HARD_LIMIT_RULE_IDS)
    assert (
        df["dominant_rule_id"].astype(str) != df["subsumed_rule_id"].astype(str)
    ).all()
    ranks = df["priority_rank"].astype(int)
    assert (ranks >= 1).all()
    assert (df["active_by_default"].astype(str).str.upper().isin(["TRUE", "FALSE"])).all()


def test_alert_hierarchy_liquidity_crisis_rows_exist():
    df = load_alert_hierarchy()
    liq = df[
        (df["environment_state"].astype(str) == "liquidity_crisis")
        & (df["active_by_default"].astype(str).str.upper() == "TRUE")
    ]
    assert not liq.empty
    pairs = set(
        zip(
            liq["dominant_rule_id"].astype(str),
            liq["subsumed_rule_id"].astype(str),
        )
    )
    assert ("liquidity_stress", "credit_stress") in pairs


def test_alert_hierarchy_covers_all_required_environment_ids():
    from src.data.config_loader import REQUIRED_ENVIRONMENT_IDS, load_alert_hierarchy

    df = load_alert_hierarchy()
    covered = set(df["environment_state"].astype(str).str.strip())
    missing = REQUIRED_ENVIRONMENT_IDS - covered
    assert not missing, f"alert_hierarchy missing environment_state rows for: {sorted(missing)}"


def test_environment_states_escalation_wording_aligned_with_step19():
    from src.data.config_loader import load_environment_states

    df = load_environment_states()
    text = "\n".join(df["escalation_meaning"].astype(str))
    assert "red if VIX >= 30 or paired stress" not in text

    vol = df.loc[df["environment_id"] == "volatility_stress", "escalation_meaning"].iloc[0]
    assert "VIX >= 30 is confirmed by VIX spike or equity stress" in str(vol)

    risk_off = df.loc[
        df["environment_id"] == "risk_off_equity_stress", "escalation_meaning"
    ].iloc[0]
    risk_off_text = str(risk_off).lower()
    assert "red risk_off only with linked spy drawdown" in risk_off_text
    assert "separate hard-limit" in risk_off_text
    assert "var breach also present" not in risk_off_text
    assert "red if drawdown or var breach" not in risk_off_text

    rates = df.loc[
        df["environment_id"] == "rates_inflation_shock", "escalation_meaning"
    ].iloc[0]
    rates_text = str(rates).lower()
    assert "inflation_pressure" in rates_text
    assert "hard_limit_red" in rates_text or "hard-limit" in rates_text


def test_alert_hierarchy_no_drawdown_subsumption_in_risk_off():
    df = load_alert_hierarchy()
    risk_off_rows = df[df["environment_state"].astype(str) == "risk_off_equity_stress"]
    subsumed = set(risk_off_rows["subsumed_rule_id"].astype(str))
    assert "drawdown_breach" not in subsumed
    assert "var_breach" not in subsumed


def test_config_files_exist_on_disk():
    for name in (
        "holdings.csv",
        "strategy_library.csv",
        "etf_universe.csv",
        "strategy_scoring_policy.csv",
        "regime_rules.csv",
        "regime_thresholds.csv",
        "factor_mapping.csv",
        "metric_status_policy.csv",
        "environment_states.csv",
        "alert_hierarchy.csv",
    ):
        assert (DEFAULT_CONFIG_DIR / name).exists()
