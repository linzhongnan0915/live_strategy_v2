"""
Observable ETF proxy factor model (prototype).

What: Map benchmark holdings to ETF factor proxies and attribute recent factor moves.
Why: Support dashboard factor view without claiming Barra or commercial factor risk.
Inputs: factor_mapping.csv, sample_price_history.csv, holdings.csv.
Outputs: Factor snapshot with exposure, factor_return, contribution_to_return.
Pitfalls: Proxies are correlated; overlapping SPY/QQQ sleeves double-count conceptually.
"""

from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from src.data.config_loader import load_all_configs, load_factor_mapping
from src.portfolio.metrics_builder import (
    compute_simple_return,
    load_price_history,
    pivot_close_prices,
)

SNAPSHOT_COLUMNS = [
    "factor_id",
    "factor_name",
    "proxy_ticker",
    "factor_group",
    "exposure",
    "factor_return",
    "contribution_to_return",
    "interpretation",
]

FACTOR_LOADING_COLUMNS = [
    "ticker",
    "asset_class",
    "risk_bucket",
    "factor_id",
    "factor_name",
    "loading",
    "loading_source",
]

FACTOR_RISK_COLUMNS = [
    "factor_id",
    "factor_name",
    "factor_group",
    "proxy_ticker",
    "portfolio_exposure",
    "proxy_volatility_20d",
    "risk_score",
    "risk_contribution_pct",
    "interpretation",
]

DEFAULT_FACTOR_RETURN_LOOKBACK = 5
DEFAULT_FACTOR_VOL_LOOKBACK = 20

FACTOR_ALIASES = {
    "economic_growth": "equity_beta",
    "equity_beta": "equity_beta",
    "growth_tech": "growth_tech",
    "size_premium": "small_cap_cyclical",
    "cyclical_beta": "small_cap_cyclical",
    "real_rates": "duration_rates",
    "duration": "duration_rates",
    "credit_risk": "high_yield_credit",
    "liquidity": "short_rates_cash",
    "liquidity_stress": "short_rates_cash",
    "inflation": "inflation_linked",
    "commodities": "oil_energy",
    "commodity": "oil_energy",
    "geopolitical": "safe_haven_gold",
    "usd": "usd_factor",
    "em_risk": "usd_factor",
    "volatility": "volatility",
    "low_volatility": "volatility",
    "quality": "equity_beta",
    "defensive_quality": "equity_beta",
    "value": "equity_beta",
    "momentum": "growth_tech",
}


def _resolve_as_of(close_df: pd.DataFrame, as_of_date: str | None) -> pd.Timestamp:
    if as_of_date is None:
        return close_df.index.max()
    ts = pd.Timestamp(as_of_date)
    if ts not in close_df.index:
        raise ValueError(f"as_of_date {as_of_date} not found in price history")
    return ts


def compute_factor_returns(
    close_df: pd.DataFrame,
    factor_mapping_df: pd.DataFrame,
    lookback: int = DEFAULT_FACTOR_RETURN_LOOKBACK,
    as_of_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Compute simple returns for each factor proxy over lookback days ending at as_of_date.

    VIX uses percent return on VIX level (volatility proxy, not a portfolio holding).
    """
    as_of = _resolve_as_of(close_df, str(as_of_date) if as_of_date is not None else None)
    rows: list[dict] = []
    for _, row in factor_mapping_df.iterrows():
        ticker = str(row["proxy_ticker"]).strip()
        if ticker not in close_df.columns:
            raise ValueError(f"factor proxy ticker missing from price history: {ticker}")
        factor_return = compute_simple_return(close_df, ticker, lookback, as_of)
        rows.append(
            {
                "factor_id": row["factor_id"],
                "proxy_ticker": ticker,
                "factor_return": factor_return,
            }
        )
    return pd.DataFrame(rows)


def compute_portfolio_factor_exposures(
    holdings_df: pd.DataFrame,
    factor_mapping_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prototype exposure: target_weight on proxy ticker if held, else 0.

    VIX and other non-held proxies receive exposure 0 by design.
    """
    weights = holdings_df.set_index("ticker")["target_weight"].astype(float)
    rows: list[dict] = []
    for _, row in factor_mapping_df.iterrows():
        ticker = str(row["proxy_ticker"]).strip()
        exposure = float(weights[ticker]) if ticker in weights.index else 0.0
        rows.append(
            {
                "factor_id": row["factor_id"],
                "proxy_ticker": ticker,
                "exposure": exposure,
            }
        )
    return pd.DataFrame(rows)


def compute_factor_contribution_to_return(
    factor_returns_df: pd.DataFrame,
    exposures_df: pd.DataFrame,
) -> pd.DataFrame:
    """Contribution = exposure * factor_return (prototype linear attribution)."""
    merged = exposures_df.merge(
        factor_returns_df[["factor_id", "factor_return"]],
        on="factor_id",
        how="inner",
    )
    merged["contribution_to_return"] = merged["exposure"] * merged["factor_return"]
    return merged[["factor_id", "exposure", "factor_return", "contribution_to_return"]]


def build_factor_snapshot(
    price_path: Path | str | None = None,
    config_dir: Path | str | None = None,
    as_of_date: str | None = None,
    lookback: int = DEFAULT_FACTOR_RETURN_LOOKBACK,
    expected_source: str | None = "sample_synthetic",
) -> pd.DataFrame:
    """
    Build full factor attribution table for dashboard and reporting.

    Observable ETF proxy model only; not a Barra or commercial risk model.
    """
    prices = load_price_history(price_path, expected_source=expected_source)
    close_df = pivot_close_prices(prices)
    as_of = _resolve_as_of(close_df, as_of_date)
    hist = close_df.loc[close_df.index <= as_of]

    if len(hist) < lookback + 1:
        raise ValueError(
            f"insufficient price history for factor return lookback {lookback}"
        )

    configs = load_all_configs(config_dir)
    mapping = configs["factor_mapping"]
    factor_returns = compute_factor_returns(hist, mapping, lookback, as_of)
    exposures = compute_portfolio_factor_exposures(configs["holdings"], mapping)
    contrib = compute_factor_contribution_to_return(factor_returns, exposures)

    snapshot = mapping.merge(contrib, on="factor_id", how="inner")
    snapshot = snapshot[
        [
            "factor_id",
            "factor_name",
            "proxy_ticker",
            "factor_group",
            "exposure",
            "factor_return",
            "contribution_to_return",
            "interpretation",
        ]
    ]
    return snapshot


def compute_etf_factor_loadings(
    etf_universe_df: pd.DataFrame,
    factor_mapping_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build observable ETF proxy factor loadings from universe metadata.

    This is a Barra-style proxy matrix: it maps ETF economic labels to factor
    proxy ids. It is not a proprietary Barra loading estimate.
    """
    factor_names = factor_mapping_df.set_index("factor_id")["factor_name"].to_dict()
    rows: list[dict] = []
    for _, row in etf_universe_df.iterrows():
        ticker = str(row["ticker"]).strip()
        if str(row.get("implementation_role", "")).strip() == "high_risk_prototype":
            continue
        for source_col, loading in (("primary_factor", 1.0), ("secondary_factor", 0.5)):
            raw = str(row.get(source_col, "")).strip().lower()
            factor_id = FACTOR_ALIASES.get(raw)
            if not factor_id or factor_id not in factor_names:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "asset_class": row.get("asset_class"),
                    "risk_bucket": row.get("risk_bucket"),
                    "factor_id": factor_id,
                    "factor_name": factor_names[factor_id],
                    "loading": loading,
                    "loading_source": source_col,
                }
            )
    if not rows:
        return pd.DataFrame(columns=FACTOR_LOADING_COLUMNS)
    loadings = pd.DataFrame(rows)
    loadings = (
        loadings.sort_values(["ticker", "factor_id", "loading"], ascending=[True, True, False])
        .drop_duplicates(["ticker", "factor_id"], keep="first")
        .reset_index(drop=True)
    )
    return loadings[FACTOR_LOADING_COLUMNS]


def compute_factor_proxy_volatility(
    close_df: pd.DataFrame,
    factor_mapping_df: pd.DataFrame,
    *,
    as_of_date: str | None = None,
    lookback: int = DEFAULT_FACTOR_VOL_LOOKBACK,
) -> pd.DataFrame:
    """Estimate recent factor proxy volatility from ETF/index proxy returns."""
    as_of = _resolve_as_of(close_df, as_of_date)
    hist = close_df.loc[close_df.index <= as_of]
    rows: list[dict] = []
    for _, row in factor_mapping_df.iterrows():
        ticker = str(row["proxy_ticker"]).strip()
        if ticker not in hist.columns:
            raise ValueError(f"factor proxy ticker missing from price history: {ticker}")
        returns = hist[ticker].pct_change().dropna().tail(lookback)
        volatility = float(returns.std()) if len(returns) else 0.0
        rows.append(
            {
                "factor_id": row["factor_id"],
                "proxy_ticker": ticker,
                "proxy_volatility_20d": volatility,
            }
        )
    return pd.DataFrame(rows)


def compute_factor_risk_contribution(
    portfolio_weights_df: pd.DataFrame,
    loadings_df: pd.DataFrame,
    factor_mapping_df: pd.DataFrame,
    factor_vol_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute simple factor risk contribution from weights, loadings, and proxy vol."""
    weights = portfolio_weights_df[["ticker", "weight"]].copy()
    weights["weight"] = weights["weight"].astype(float)
    merged = loadings_df.merge(weights, on="ticker", how="inner")
    if merged.empty:
        return pd.DataFrame(columns=FACTOR_RISK_COLUMNS)
    merged["weighted_loading"] = merged["weight"] * merged["loading"].astype(float)
    exposure = (
        merged.groupby("factor_id", as_index=False)["weighted_loading"]
        .sum()
        .rename(columns={"weighted_loading": "portfolio_exposure"})
    )
    risk = (
        factor_mapping_df.merge(exposure, on="factor_id", how="left")
        .merge(factor_vol_df, on=["factor_id", "proxy_ticker"], how="left")
    )
    risk["portfolio_exposure"] = risk["portfolio_exposure"].fillna(0.0)
    risk["proxy_volatility_20d"] = risk["proxy_volatility_20d"].fillna(0.0)
    risk["risk_score"] = (
        risk["portfolio_exposure"].abs() * risk["proxy_volatility_20d"]
    )
    total = float(risk["risk_score"].sum())
    risk["risk_contribution_pct"] = (
        risk["risk_score"] / total * 100.0 if total > 0 else 0.0
    )
    return risk[FACTOR_RISK_COLUMNS].sort_values(
        "risk_contribution_pct", ascending=False
    ).reset_index(drop=True)


def portfolio_weights_from_simulation(
    simulation_path: Path | str,
) -> pd.DataFrame:
    """Read current selected-sleeve weights from portfolio simulation JSON."""
    path = Path(simulation_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = [
        {"ticker": item["ticker"], "weight": float(item.get("sleeve_weight", 0.0))}
        for item in payload.get("current_holdings", [])
    ]
    return pd.DataFrame(rows)


def build_barra_style_factor_risk_snapshot(
    price_path: Path | str | None = None,
    config_dir: Path | str | None = None,
    simulation_path: Path | str | None = None,
    as_of_date: str | None = None,
    expected_source: str | None = None,
) -> dict:
    """Build dashboard-ready Barra-style ETF proxy risk snapshot."""
    prices = load_price_history(price_path, expected_source=expected_source)
    close_df = pivot_close_prices(prices)
    configs = load_all_configs(config_dir)
    mapping = configs["factor_mapping"]
    loadings = compute_etf_factor_loadings(configs["etf_universe"], mapping)
    factor_vol = compute_factor_proxy_volatility(close_df, mapping, as_of_date=as_of_date)
    if simulation_path and Path(simulation_path).exists():
        weights = portfolio_weights_from_simulation(simulation_path)
    else:
        weights = configs["holdings"][["ticker", "target_weight"]].rename(
            columns={"target_weight": "weight"}
        )
    risk = compute_factor_risk_contribution(weights, loadings, mapping, factor_vol)
    strategy_notes = configs["strategy_library"][
        [
            "strategy_id",
            "strategy_name",
            "category",
            "objective",
            "target_etfs",
            "primary_factor",
            "secondary_factor",
            "core_signal",
            "risk_controls",
            "failure_mode",
        ]
    ].copy()
    return {
        "data_mode": "barra_style_blackrock_factor_proxy",
        "model_disclaimer": (
            "Observable ETF proxy factor model. Barra-style risk lens and "
            "BlackRock-style factor-to-assets mapping; not a commercial Barra model."
        ),
        "factor_loading_matrix": loadings.to_dict(orient="records"),
        "factor_risk_contribution": risk.to_dict(orient="records"),
        "blackrock_factor_sleeves": strategy_notes.to_dict(orient="records"),
    }
