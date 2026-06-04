"""
Build rule-engine metrics snapshots from sample or processed price history.

What: Compute returns, drawdowns, portfolio risk proxies from close prices.
Why: Move from hand-written mock JSON to reproducible prototype metrics.
Inputs: sample_price_history.csv, holdings weights from config.
Outputs: JSON-compatible dict for src.regime.rule_engine.
Pitfalls: headline/strategy drift are placeholders until vendor feeds exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.config_loader import PROJECT_ROOT, load_all_configs

DEFAULT_PRICE_PATH = PROJECT_ROOT / "data" / "samples" / "sample_price_history.csv"
COMPUTED_DATA_SOURCE = "sample_synthetic_computed_from_prices"
EXPECTED_PRICE_SOURCE = "sample_synthetic"
ALLOWED_PRICE_SOURCES = frozenset({"sample_synthetic", "openbb_yfinance"})

PRICE_COLUMNS = ["date", "ticker", "close", "source"]

REQUIRED_PRICE_TICKERS = [
    "SPY",
    "QQQ",
    "IWM",
    "TLT",
    "IEF",
    "SHY",
    "HYG",
    "LQD",
    "TIP",
    "GLD",
    "USO",
    "UUP",
    "VIX",
]

# Prototype placeholders only (not computed from prices; not live market data).
PROTOTYPE_HEADLINE_SEVERITY = 0
PROTOTYPE_STRATEGY_RETURN_DEVIATION = 0.0

METRIC_RETURN_LOOKBACK = 5
METRIC_DRAWDOWN_LOOKBACK = 20
METRIC_PORTFOLIO_VAR_LOOKBACK = 20
DEFAULT_VAR_LIMIT = 0.02
DEFAULT_VAR_CONFIDENCE = 0.95


def load_price_history(
    path: Path | str | None = None,
    expected_source: str | None = EXPECTED_PRICE_SOURCE,
) -> pd.DataFrame:
    """Load long-format price history CSV."""
    file_path = Path(path) if path else DEFAULT_PRICE_PATH
    if not file_path.exists():
        raise FileNotFoundError(f"Price history not found: {file_path}")
    df = pd.read_csv(file_path)
    validate_price_history(df, expected_source=expected_source)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "ticker"]).reset_index(drop=True)


def validate_price_history(
    df: pd.DataFrame,
    required_tickers: list[str] | None = None,
    expected_source: str | None = EXPECTED_PRICE_SOURCE,
) -> None:
    """Validate schema, source tag, required tickers, and complete close panel."""
    if list(df.columns) != PRICE_COLUMNS:
        raise ValueError(f"price history columns must be {PRICE_COLUMNS}; got {list(df.columns)}")
    if df.empty:
        raise ValueError("price history is empty")
    sources = df["source"].astype(str)
    unknown = set(sources.unique()) - ALLOWED_PRICE_SOURCES
    if unknown:
        raise ValueError(
            f"price history source must be one of {sorted(ALLOWED_PRICE_SOURCES)}; "
            f"got unknown: {sorted(unknown)}"
        )
    if expected_source is not None:
        if expected_source not in ALLOWED_PRICE_SOURCES:
            raise ValueError(
                f"expected_source must be one of {sorted(ALLOWED_PRICE_SOURCES)} "
                f"or None; got {expected_source!r}"
            )
        if not (sources == expected_source).all():
            raise ValueError(
                f"price history source must be {expected_source} for all rows"
            )
    tickers = required_tickers or REQUIRED_PRICE_TICKERS
    present = set(df["ticker"].astype(str).unique())
    missing = [t for t in tickers if t not in present]
    if missing:
        raise ValueError(f"price history missing required tickers: {missing}")
    if df["close"].isna().any():
        raise ValueError("price history contains missing close values")
    dates = df["date"].nunique()
    expected_rows = dates * len(tickers)
    if len(df) != expected_rows:
        raise ValueError(
            "price history must have one close per ticker per date; "
            f"expected {expected_rows} rows, got {len(df)}"
        )


def derive_computed_data_source(price_df: pd.DataFrame) -> str:
    """Map validated price source tags to snapshot data_source label."""
    sources = set(price_df["source"].astype(str).unique())
    if sources == {EXPECTED_PRICE_SOURCE}:
        return COMPUTED_DATA_SOURCE
    if sources == {"openbb_yfinance"}:
        return "openbb_yfinance_computed_from_prices"
    return "mixed_allowed_sources_computed_from_prices"


def pivot_close_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot to date index and ticker columns of close prices."""
    wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    if wide.isna().any().any():
        raise ValueError("price history has missing close values after pivot")
    return wide


def _resolve_as_of_date(close_df: pd.DataFrame, as_of_date: str | None) -> pd.Timestamp:
    if as_of_date is None:
        return close_df.index.max()
    ts = pd.Timestamp(as_of_date)
    if ts not in close_df.index:
        raise ValueError(f"as_of_date {as_of_date} not found in price history")
    return ts


def _history_to_as_of(close_df: pd.DataFrame, as_of_date: pd.Timestamp) -> pd.DataFrame:
    """No look-ahead: restrict to dates up to and including as_of_date."""
    return close_df.loc[close_df.index <= as_of_date].copy()


def compute_simple_return(
    close_df: pd.DataFrame,
    ticker: str,
    lookback: int,
    as_of_date: pd.Timestamp | None = None,
) -> float:
    """Simple return over lookback trading days ending at as_of_date."""
    as_of = _resolve_as_of_date(close_df, str(as_of_date) if as_of_date is not None else None)
    hist = _history_to_as_of(close_df, as_of)
    if ticker not in hist.columns:
        raise ValueError(f"ticker {ticker} not in price history")
    dates = hist.index
    loc = dates.get_loc(as_of)
    if loc < lookback:
        raise ValueError(
            f"insufficient history for {ticker} lookback {lookback} at {as_of.date()}"
        )
    end_price = float(hist.loc[as_of, ticker])
    start_price = float(hist.iloc[loc - lookback][ticker])
    return end_price / start_price - 1.0


def compute_drawdown(
    close_df: pd.DataFrame,
    ticker: str,
    lookback: int,
    as_of_date: pd.Timestamp | None = None,
) -> float:
    """Peak-to-trough drawdown over lookback window ending at as_of_date (<= 0)."""
    as_of = _resolve_as_of_date(close_df, str(as_of_date) if as_of_date is not None else None)
    hist = _history_to_as_of(close_df, as_of)
    if ticker not in hist.columns:
        raise ValueError(f"ticker {ticker} not in price history")
    if len(hist) < lookback + 1:
        raise ValueError(
            f"insufficient history for {ticker} drawdown lookback {lookback}"
        )
    window = hist[ticker].iloc[-(lookback + 1) :]
    peak = float(window.max())
    current = float(hist.loc[as_of, ticker])
    if peak <= 0:
        raise ValueError(f"invalid peak price for {ticker}")
    return current / peak - 1.0


def compute_vix_level(
    close_df: pd.DataFrame,
    as_of_date: pd.Timestamp | None = None,
) -> float:
    """Latest VIX close at as_of_date (index level, not a return)."""
    as_of = _resolve_as_of_date(close_df, str(as_of_date) if as_of_date is not None else None)
    hist = _history_to_as_of(close_df, as_of)
    if "VIX" not in hist.columns:
        raise ValueError("VIX missing from price history")
    return float(hist.loc[as_of, "VIX"])


def compute_vix_change(
    close_df: pd.DataFrame,
    as_of_date: pd.Timestamp | None = None,
) -> float:
    """
    One-day VIX change in index points (not percent).

    Current close minus prior trading day close, using data <= as_of_date only.
    """
    as_of = _resolve_as_of_date(close_df, str(as_of_date) if as_of_date is not None else None)
    hist = _history_to_as_of(close_df, as_of)
    if "VIX" not in hist.columns:
        raise ValueError("VIX missing from price history")
    dates = hist.index
    loc = dates.get_loc(as_of)
    if loc < 1:
        raise ValueError(
            f"insufficient VIX history for change at {as_of.date()}; need prior trading day"
        )
    current = float(hist.loc[as_of, "VIX"])
    prior = float(hist.iloc[loc - 1]["VIX"])
    return current - prior


def compute_relative_return(
    close_df: pd.DataFrame,
    long_ticker: str,
    short_ticker: str,
    lookback: int,
    as_of_date: pd.Timestamp | None = None,
) -> float:
    """Return difference: long_ticker return minus short_ticker return."""
    long_ret = compute_simple_return(close_df, long_ticker, lookback, as_of_date)
    short_ret = compute_simple_return(close_df, short_ticker, lookback, as_of_date)
    return long_ret - short_ret


def compute_portfolio_returns(
    close_df: pd.DataFrame,
    holdings_df: pd.DataFrame,
) -> pd.Series:
    """
    Daily portfolio simple returns using benchmark target_weight.

    Only holdings tickers with price data and positive target_weight are used.
    Weights are renormalized to sum to 1.0 over that overlap (XLK etc. excluded
    when absent from price file).
    """
    returns = close_df.pct_change()
    weights = holdings_df.set_index("ticker")["target_weight"].astype(float)
    overlap = [t for t in weights.index if t in returns.columns and weights[t] > 0]
    if not overlap:
        raise ValueError("no overlapping tickers between holdings and price history")
    w = weights.loc[overlap]
    w = w / w.sum()
    # min_count=1: all-NaN rows (first date after pct_change) stay NaN, not 0.0
    port = returns[overlap].mul(w, axis=1).sum(axis=1, min_count=1).dropna()
    port.name = "portfolio_return"
    return port


def compute_portfolio_drawdown(
    portfolio_returns: pd.Series,
    lookback: int,
    as_of_date: pd.Timestamp | None = None,
) -> float:
    """Drawdown on cumulative portfolio NAV ending at as_of_date."""
    as_of = _resolve_as_of_date(
        portfolio_returns.to_frame("portfolio_return"),
        str(as_of_date) if as_of_date is not None else None,
    )
    hist = portfolio_returns.loc[portfolio_returns.index <= as_of]
    if len(hist) < lookback + 1:
        raise ValueError(
            f"insufficient portfolio return history for drawdown lookback {lookback}"
        )
    nav = (1.0 + hist).cumprod()
    window = nav.iloc[-(lookback + 1) :]
    peak = float(window.max())
    current = float(nav.loc[as_of])
    return current / peak - 1.0


def compute_historical_var_ratio(
    portfolio_returns: pd.Series,
    lookback: int = METRIC_PORTFOLIO_VAR_LOOKBACK,
    confidence: float = DEFAULT_VAR_CONFIDENCE,
    var_limit: float = DEFAULT_VAR_LIMIT,
    as_of_date: pd.Timestamp | None = None,
) -> float:
    """
    Historical daily VaR as a ratio to var_limit for regime threshold comparison.

    Method:
    - Use portfolio daily simple returns over the last `lookback` days ending at as_of_date.
    - Estimate one-day VaR as the absolute value of the (1 - confidence) lower quantile
      of those returns (loss magnitude, e.g. 5% tail for confidence=0.95).
    - Return estimated_var / var_limit so thresholds like portfolio VaR >= 1.0 mean
      estimated loss exceeds the internal daily limit.
    """
    as_of = _resolve_as_of_date(
        portfolio_returns.to_frame("portfolio_return"),
        str(as_of_date) if as_of_date is not None else None,
    )
    hist = portfolio_returns.loc[portfolio_returns.index <= as_of]
    window = hist.tail(lookback)
    if len(window) < lookback:
        raise ValueError(
            f"insufficient portfolio return history for VaR lookback {lookback}"
        )
    quantile = float(window.quantile(1.0 - confidence))
    estimated_var = max(0.0, -quantile)
    if var_limit <= 0:
        raise ValueError("var_limit must be positive")
    return estimated_var / var_limit


def _compute_cross_asset_confirmation(
    close_df: pd.DataFrame,
    as_of_date: pd.Timestamp,
    lookback: int = METRIC_RETURN_LOOKBACK,
) -> int:
    """
    Count price-based stress confirmation legs (prototype logic).

    Legs: SPY down, GLD up, UUP up, USO up, TLT down, HYG underperforms LQD.
    """
    legs = 0
    checks: list[tuple[str, Any]] = [
        ("SPY", lambda r: r < 0),
        ("GLD", lambda r: r > 0),
        ("UUP", lambda r: r > 0),
        ("USO", lambda r: r > 0),
        ("TLT", lambda r: r < 0),
    ]
    for ticker, rule in checks:
        ret = compute_simple_return(close_df, ticker, lookback, as_of_date)
        if rule(ret):
            legs += 1
    rel = compute_relative_return(close_df, "HYG", "LQD", lookback, as_of_date)
    if rel < 0:
        legs += 1
    return legs


def build_metrics_snapshot(
    price_path: Path | str | None = None,
    config_dir: Path | str | None = None,
    as_of_date: str | None = None,
    expected_source: str | None = EXPECTED_PRICE_SOURCE,
) -> dict[str, Any]:
    """
    Build metrics JSON payload from price history and holdings config.

    All price-derived metrics are computed from data up to as_of_date only.
    """
    prices = load_price_history(price_path, expected_source=expected_source)
    data_source = derive_computed_data_source(prices)
    configs = load_all_configs(config_dir)
    holdings = configs["holdings"]

    close_df = pivot_close_prices(prices)
    as_of = _resolve_as_of_date(close_df, as_of_date)
    hist = _history_to_as_of(close_df, as_of)

    min_rows = max(
        METRIC_RETURN_LOOKBACK,
        METRIC_DRAWDOWN_LOOKBACK,
        METRIC_PORTFOLIO_VAR_LOOKBACK,
    ) + 1
    if len(hist) < min_rows:
        raise ValueError(
            f"need at least {min_rows} trading dates through as_of_date; got {len(hist)}"
        )

    port_returns = compute_portfolio_returns(hist, holdings)

    metrics: dict[str, float | int] = {
        "VIX level": compute_vix_level(close_df, as_of),
        "VIX change": compute_vix_change(close_df, as_of),
        "headline severity": PROTOTYPE_HEADLINE_SEVERITY,
        "strategy return deviation": PROTOTYPE_STRATEGY_RETURN_DEVIATION,
    }

    return_tickers = [t for t in REQUIRED_PRICE_TICKERS if t != "VIX"]
    for ticker in return_tickers:
        if ticker not in hist.columns:
            raise ValueError(f"required ticker {ticker} missing at as_of_date")
        metrics[f"{ticker} return"] = compute_simple_return(
            close_df, ticker, METRIC_RETURN_LOOKBACK, as_of
        )

    metrics["HYG vs LQD relative return"] = compute_relative_return(
        close_df, "HYG", "LQD", METRIC_RETURN_LOOKBACK, as_of
    )
    metrics["SPY drawdown"] = compute_drawdown(
        close_df, "SPY", METRIC_DRAWDOWN_LOOKBACK, as_of
    )
    metrics["portfolio drawdown"] = compute_portfolio_drawdown(
        port_returns, METRIC_DRAWDOWN_LOOKBACK, as_of
    )
    metrics["portfolio VaR"] = compute_historical_var_ratio(
        port_returns,
        lookback=METRIC_PORTFOLIO_VAR_LOOKBACK,
        as_of_date=as_of,
    )
    metrics["cross-asset confirmation count"] = _compute_cross_asset_confirmation(
        close_df, as_of, METRIC_RETURN_LOOKBACK
    )

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    return {
        "as_of_date": as_of.strftime("%Y-%m-%d"),
        "data_source": data_source,
        "timestamp": timestamp,
        "metrics": metrics,
    }


def snapshot_to_jsonable(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Convert metric values to plain JSON floats."""
    out = dict(snapshot)
    out["metrics"] = {
        k: float(v) if isinstance(v, (np.floating, float)) else v
        for k, v in snapshot["metrics"].items()
    }
    return out
