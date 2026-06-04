"""Tests for observable ETF proxy factor model."""

import pandas as pd
import pytest

from src.data.config_loader import load_holdings
from src.factors.factor_model import (
    DEFAULT_FACTOR_RETURN_LOOKBACK,
    FACTOR_LOADING_COLUMNS,
    FACTOR_RISK_COLUMNS,
    SNAPSHOT_COLUMNS,
    build_barra_style_factor_risk_snapshot,
    build_factor_snapshot,
    compute_etf_factor_loadings,
    compute_factor_contribution_to_return,
    compute_factor_risk_contribution,
    compute_factor_proxy_volatility,
    compute_factor_returns,
    compute_portfolio_factor_exposures,
    load_factor_mapping,
)
from src.data.config_loader import load_all_configs
from src.portfolio.metrics_builder import (
    load_price_history,
    pivot_close_prices,
)


def test_factor_mapping_loads_thirteen_factors():
    mapping = load_factor_mapping()
    assert len(mapping) == 13
    assert mapping["factor_id"].nunique() == 13


def test_proxy_tickers_exist_in_sample_prices():
    mapping = load_factor_mapping()
    prices = load_price_history()
    tickers = set(prices["ticker"].unique())
    for ticker in mapping["proxy_ticker"]:
        assert ticker in tickers


def test_factor_returns_non_empty():
    mapping = load_factor_mapping()
    close_df = pivot_close_prices(load_price_history())
    returns = compute_factor_returns(close_df, mapping, lookback=5)
    assert len(returns) == 13
    assert returns["factor_return"].notna().all()


def test_exposures_use_holdings_weights():
    mapping = load_factor_mapping()
    holdings = load_holdings()
    exposures = compute_portfolio_factor_exposures(holdings, mapping)
    spy = exposures.loc[exposures["proxy_ticker"] == "SPY", "exposure"].iloc[0]
    assert spy == pytest.approx(0.10)


def test_vix_exposure_zero_when_not_in_holdings():
    mapping = load_factor_mapping()
    holdings = load_holdings()
    exposures = compute_portfolio_factor_exposures(holdings, mapping)
    vix = exposures.loc[exposures["proxy_ticker"] == "VIX", "exposure"].iloc[0]
    assert vix == 0.0
    assert "VIX" not in set(holdings["ticker"])


def test_contribution_equals_exposure_times_return():
    mapping = load_factor_mapping()
    holdings = load_holdings()
    close_df = pivot_close_prices(load_price_history())
    returns = compute_factor_returns(close_df, mapping, lookback=5)
    exposures = compute_portfolio_factor_exposures(holdings, mapping)
    contrib = compute_factor_contribution_to_return(returns, exposures)
    expected = contrib["exposure"] * contrib["factor_return"]
    assert contrib["contribution_to_return"].equals(expected)


def test_build_factor_snapshot_required_columns():
    snapshot = build_factor_snapshot()
    assert list(snapshot.columns) == SNAPSHOT_COLUMNS
    assert len(snapshot) == 13


def test_no_look_ahead_factor_returns_differ():
    close_df = pivot_close_prices(load_price_history())
    mapping = load_factor_mapping()
    dates = close_df.index.sort_values()
    early = dates[21]
    late = dates[-1]
    r_early = compute_factor_returns(
        close_df, mapping, DEFAULT_FACTOR_RETURN_LOOKBACK, early
    )
    r_late = compute_factor_returns(
        close_df, mapping, DEFAULT_FACTOR_RETURN_LOOKBACK, late
    )
    spy_early = r_early.loc[r_early["proxy_ticker"] == "SPY", "factor_return"].iloc[0]
    spy_late = r_late.loc[r_late["proxy_ticker"] == "SPY", "factor_return"].iloc[0]
    assert spy_early != spy_late


def test_missing_proxy_ticker_raises():
    mapping = load_factor_mapping()
    close_df = pivot_close_prices(load_price_history()).drop(columns=["SPY"])
    with pytest.raises(ValueError, match="SPY"):
        compute_factor_returns(close_df, mapping, lookback=5)


def test_etf_factor_loading_matrix_has_required_columns():
    configs = load_all_configs()
    loadings = compute_etf_factor_loadings(
        configs["etf_universe"], configs["factor_mapping"]
    )

    assert list(loadings.columns) == FACTOR_LOADING_COLUMNS
    assert not loadings.empty
    spy = loadings[loadings["ticker"] == "SPY"]
    assert "equity_beta" in set(spy["factor_id"])


def test_factor_risk_contribution_sums_to_roughly_100():
    configs = load_all_configs()
    close_df = pivot_close_prices(load_price_history())
    loadings = compute_etf_factor_loadings(
        configs["etf_universe"], configs["factor_mapping"]
    )
    vol = compute_factor_proxy_volatility(close_df, configs["factor_mapping"])
    weights = configs["holdings"][["ticker", "target_weight"]].rename(
        columns={"target_weight": "weight"}
    )
    risk = compute_factor_risk_contribution(
        weights, loadings, configs["factor_mapping"], vol
    )

    assert list(risk.columns) == FACTOR_RISK_COLUMNS
    assert risk["risk_contribution_pct"].sum() == pytest.approx(100.0)
    assert risk.iloc[0]["risk_score"] >= risk.iloc[-1]["risk_score"]


def test_barra_style_snapshot_contains_disclaimer_and_sleeves():
    snapshot = build_barra_style_factor_risk_snapshot()

    assert "not a commercial Barra model" in snapshot["model_disclaimer"]
    assert snapshot["factor_loading_matrix"]
    assert snapshot["factor_risk_contribution"]
    assert snapshot["blackrock_factor_sleeves"]
