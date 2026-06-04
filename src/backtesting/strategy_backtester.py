"""
Baseline ETF sleeve backtests for the 20-strategy demo.

This module compares strategy baskets. It is not signal-conditioned alpha
validation and does not generate trade recommendations.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.config_loader import PROJECT_ROOT, load_etf_universe, load_strategy_library
from src.portfolio.metrics_builder import DEFAULT_PRICE_PATH, PRICE_COLUMNS

DEFAULT_PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
DEFAULT_RAW_PATH = PROJECT_ROOT / "data" / "raw" / "openbb_price_history.csv"
TRADING_DAYS_PER_YEAR = 252

REQUIRED_BACKTEST_COLUMNS = [
    "final_backtest_rank",
    "final_backtest_score",
    "backtest_status",
    "strategy_id",
    "category",
    "target_etfs",
    "available_price_etfs",
    "missing_price_etfs",
    "price_coverage_ratio",
    "price_coverage_status",
    "total_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe_proxy",
    "max_drawdown",
    "win_rate_daily",
    "win_rate_monthly",
    "positive_month_count",
    "negative_month_count",
    "observation_count",
    "benchmark_relative_return_vs_SPY",
    "rank_by_total_return",
    "rank_by_sharpe",
    "rank_by_drawdown",
    "rank_by_monthly_win_rate",
    "explanation",
]

WFO_RESULT_COLUMNS = [
    "wfo_rank",
    "wfo_score",
    "wfo_status",
    "strategy_id",
    "category",
    "target_etfs",
    "available_price_etfs",
    "missing_price_etfs",
    "price_coverage_ratio",
    "price_coverage_status",
    "window_count",
    "selected_top5_window_count",
    "train_top5_hit_rate",
    "oos_avg_total_return",
    "oos_avg_sharpe",
    "oos_avg_max_drawdown",
    "oos_avg_monthly_win_rate",
    "oos_positive_window_rate",
    "selected_oos_avg_total_return",
    "selected_oos_positive_window_rate",
    "first_test_start",
    "last_test_end",
    "explanation",
]


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy NaN and infinities to JSON-safe nulls."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _read_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if list(df.columns) != PRICE_COLUMNS:
        raise ValueError(f"price history columns must be {PRICE_COLUMNS}; got {list(df.columns)}")
    if df.empty:
        raise ValueError(f"price history is empty: {path}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).copy()
    if df.empty:
        raise ValueError(f"price history has no valid date/close rows: {path}")
    return df.sort_values(["date", "ticker"]).reset_index(drop=True)


def _price_panel_metadata(prices: pd.DataFrame) -> dict[str, Any]:
    """Return basic data coverage metadata for audit display."""
    if prices.empty:
        return {
            "price_start_date": None,
            "price_end_date": None,
            "price_ticker_count": 0,
            "price_row_count": 0,
            "approx_years": 0.0,
        }
    start = pd.Timestamp(prices["date"].min())
    end = pd.Timestamp(prices["date"].max())
    duplicate_count = int(prices.duplicated(["date", "ticker"]).sum())
    unique_observations = int(prices[["date", "ticker"]].drop_duplicates().shape[0])
    source_values = (
        sorted(prices["source"].dropna().astype(str).unique().tolist())
        if "source" in prices.columns
        else []
    )
    ticker_counts = prices.groupby("ticker")["date"].nunique().sort_values()
    return {
        "price_start_date": start.date().isoformat(),
        "price_end_date": end.date().isoformat(),
        "price_ticker_count": int(prices["ticker"].nunique()),
        "price_row_count": int(len(prices)),
        "unique_ticker_date_count": unique_observations,
        "duplicate_ticker_date_count": duplicate_count,
        "duplicate_ticker_date_policy": (
            "pivot_table last close per ticker/date; duplicates disclosed for research audit"
            if duplicate_count
            else "no duplicate ticker/date observations detected"
        ),
        "source_values": source_values,
        "min_observations_per_ticker": int(ticker_counts.min()) if not ticker_counts.empty else 0,
        "max_observations_per_ticker": int(ticker_counts.max()) if not ticker_counts.empty else 0,
        "approx_years": round(float((end - start).days / 365.25), 2),
    }


def load_strategy_price_panel(price_path: Path | str | None = None) -> tuple[pd.DataFrame, str]:
    """
    Load price panel for strategy research.

    Explicit price_path wins. Otherwise prefer raw OpenBB when it has broader ETF
    coverage than processed data; this is research-only and does not alter
    official EOD risk metrics. Fall back to processed OpenBB, then sample prices.
    """
    if price_path is not None:
        path = Path(price_path)
        return _read_price_csv(path), f"custom:{path}"

    candidates: list[tuple[Path, str]] = []
    if DEFAULT_RAW_PATH.exists():
        candidates.append((DEFAULT_RAW_PATH, "openbb_raw_research"))
    if DEFAULT_PROCESSED_PATH.exists():
        candidates.append((DEFAULT_PROCESSED_PATH, "openbb_processed"))
    candidates.append((DEFAULT_PRICE_PATH, "sample_synthetic"))

    best_df: pd.DataFrame | None = None
    best_label = ""
    best_ticker_count = -1
    for path, label in candidates:
        if not path.exists():
            continue
        df = _read_price_csv(path)
        ticker_count = int(df["ticker"].nunique())
        if ticker_count > best_ticker_count:
            best_df = df
            best_label = label
            best_ticker_count = ticker_count

    if best_df is None:
        raise FileNotFoundError("No strategy price panel found")
    return best_df, best_label


def parse_target_etfs(value: Any) -> list[str]:
    """Parse semicolon-delimited target ETF list."""
    return [part.strip().upper() for part in str(value).split(";") if part.strip()]


def _investable_tickers() -> set[str]:
    """Return tickers allowed to contribute to long-only sleeve backtests."""
    universe = load_etf_universe()
    blocked_roles = {"monitor_only", "high_risk_prototype"}
    allowed = universe[
        ~universe["implementation_role"].astype(str).str.strip().isin(blocked_roles)
    ]
    return set(allowed["ticker"].astype(str).str.upper())


def _pivot_close_prices(price_df: pd.DataFrame) -> pd.DataFrame:
    wide = price_df.pivot_table(
        index="date",
        columns="ticker",
        values="close",
        aggfunc="last",
    ).sort_index()
    wide.columns = [str(col).upper() for col in wide.columns]
    return wide


def _coverage_status(ratio: float) -> str:
    if ratio >= 0.80:
        return "sufficient"
    if ratio >= 0.50:
        return "partial"
    return "insufficient"


def build_strategy_returns(
    close_df: pd.DataFrame,
    target_etfs: list[str],
    investable_tickers: set[str] | None = None,
) -> tuple[pd.Series, list[str], list[str], float, str]:
    """
    Build equal-weight daily returns for available target ETFs.

    No leverage, no shorting, no forward-fill. Missing ETF coverage is reported.
    """
    tickers = [ticker.upper() for ticker in target_etfs]
    allowed = investable_tickers or set(close_df.columns)
    available = [
        ticker
        for ticker in tickers
        if ticker in allowed and ticker in close_df.columns and close_df[ticker].notna().sum() >= 2
    ]
    missing = [ticker for ticker in tickers if ticker not in available]
    coverage_ratio = len(available) / len(tickers) if tickers else 0.0
    coverage_status = _coverage_status(coverage_ratio)

    if not available:
        empty = pd.Series(dtype=float, name="strategy_return")
        return empty, available, missing, coverage_ratio, coverage_status

    returns = close_df[available].pct_change(fill_method=None)
    strategy_returns = returns.mean(axis=1, skipna=True).dropna()
    strategy_returns.name = "strategy_return"
    return strategy_returns, available, missing, coverage_ratio, coverage_status


def _total_return(returns: pd.Series) -> float | None:
    if returns.empty:
        return None
    return float((1.0 + returns).prod() - 1.0)


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    cumulative = (1.0 + returns).cumprod()
    drawdown = cumulative / cumulative.cummax() - 1.0
    return float(drawdown.min())


def _monthly_returns(returns: pd.Series) -> pd.Series:
    if returns.empty:
        return pd.Series(dtype=float)
    monthly = (1.0 + returns).resample("ME").prod() - 1.0
    return monthly.dropna()


def _score_frame_for_ranking(metrics_df: pd.DataFrame) -> pd.Series:
    """Composite score used for baseline and WFO train-window ranking."""
    total_score = _percentile_scores(metrics_df["total_return"], higher_is_better=True)
    sharpe_score = _percentile_scores(metrics_df["sharpe_proxy"], higher_is_better=True)
    drawdown_score = _percentile_scores(metrics_df["max_drawdown"], higher_is_better=True)
    win_score = _percentile_scores(metrics_df["win_rate_monthly"], higher_is_better=True)
    return 0.35 * total_score + 0.30 * sharpe_score + 0.20 * drawdown_score + 0.15 * win_score


def compute_backtest_metrics(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> dict[str, Any]:
    """Compute baseline return, risk, and win-rate metrics."""
    if strategy_returns.empty:
        return {
            "total_return": None,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_proxy": None,
            "max_drawdown": 0.0,
            "win_rate_daily": None,
            "win_rate_monthly": None,
            "positive_month_count": 0,
            "negative_month_count": 0,
            "observation_count": 0,
            "benchmark_relative_return_vs_SPY": None,
        }

    returns = strategy_returns.dropna()
    obs = int(len(returns))
    total = _total_return(returns)
    ann_return = None
    if total is not None and total > -1.0 and obs > 0:
        ann_return = float((1.0 + total) ** (TRADING_DAYS_PER_YEAR / obs) - 1.0)
    ann_vol = float(returns.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
    sharpe = float(ann_return / ann_vol) if ann_return is not None and ann_vol > 0 else None
    monthly = _monthly_returns(returns)

    aligned_benchmark = benchmark_returns.reindex(returns.index).dropna()
    benchmark_relative = None
    if not aligned_benchmark.empty and total is not None:
        benchmark_total = _total_return(aligned_benchmark)
        if benchmark_total is not None:
            benchmark_relative = float(total - benchmark_total)

    return {
        "total_return": total,
        "annualized_return": ann_return,
        "annualized_volatility": ann_vol,
        "sharpe_proxy": sharpe,
        "max_drawdown": _max_drawdown(returns),
        "win_rate_daily": float((returns > 0).mean()),
        "win_rate_monthly": float((monthly > 0).mean()) if len(monthly) else None,
        "positive_month_count": int((monthly > 0).sum()),
        "negative_month_count": int((monthly < 0).sum()),
        "observation_count": obs,
        "benchmark_relative_return_vs_SPY": benchmark_relative,
    }


def _percentile_scores(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    filled = numeric.fillna(numeric.min() if higher_is_better else numeric.max())
    if filled.nunique() <= 1:
        return pd.Series(0.5, index=values.index)
    return filled.rank(pct=True, ascending=higher_is_better)


def rank_backtest_results(results: pd.DataFrame) -> pd.DataFrame:
    """Add metric ranks and final composite backtest rank."""
    ranked = results.copy()
    ranked["final_backtest_score"] = _score_frame_for_ranking(ranked)
    insufficient = ranked["price_coverage_ratio"].astype(float) < 0.50
    ranked.loc[insufficient, "backtest_status"] = "insufficient_data"
    ranked.loc[~insufficient, "backtest_status"] = "baseline_backtested"
    ranked.loc[insufficient, "final_backtest_score"] = ranked.loc[
        insufficient, "final_backtest_score"
    ].clip(upper=0.25)

    ranked["rank_by_total_return"] = pd.to_numeric(
        ranked["total_return"], errors="coerce"
    ).rank(method="min", ascending=False, na_option="bottom").astype(int)
    ranked["rank_by_sharpe"] = pd.to_numeric(
        ranked["sharpe_proxy"], errors="coerce"
    ).rank(method="min", ascending=False, na_option="bottom").astype(int)
    ranked["rank_by_drawdown"] = pd.to_numeric(
        ranked["max_drawdown"], errors="coerce"
    ).rank(method="min", ascending=False, na_option="bottom").astype(int)
    ranked["rank_by_monthly_win_rate"] = pd.to_numeric(
        ranked["win_rate_monthly"], errors="coerce"
    ).rank(method="min", ascending=False, na_option="bottom").astype(int)

    ranked = ranked.sort_values(
        ["final_backtest_score", "price_coverage_ratio"],
        ascending=[False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "final_backtest_rank", ranked.index + 1)
    ranked["final_backtest_score"] = ranked["final_backtest_score"].round(4)
    return ranked[REQUIRED_BACKTEST_COLUMNS]


def backtest_all_strategies(
    price_path: Path | str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Backtest all strategy ETF baskets from strategy_library.csv."""
    strategies = load_strategy_library()
    prices, price_source = load_strategy_price_panel(price_path=price_path)
    close_df = _pivot_close_prices(prices)
    investable = _investable_tickers()
    benchmark_returns = (
        close_df["SPY"].pct_change(fill_method=None).dropna()
        if "SPY" in close_df.columns
        else pd.Series(dtype=float)
    )

    rows: list[dict[str, Any]] = []
    for _, strategy in strategies.iterrows():
        tickers = parse_target_etfs(strategy["target_etfs"])
        returns, available, missing, coverage_ratio, coverage_status = build_strategy_returns(
            close_df,
            tickers,
            investable,
        )
        metrics = compute_backtest_metrics(returns, benchmark_returns)
        explanation = (
            "Baseline equal-weight ETF sleeve backtest; not signal-conditioned alpha validation."
        )
        if missing:
            explanation += f" Missing price coverage: {', '.join(missing)}."
        rows.append(
            {
                "strategy_id": str(strategy["strategy_id"]),
                "category": str(strategy["category"]),
                "target_etfs": ";".join(tickers),
                "available_price_etfs": ";".join(available),
                "missing_price_etfs": ";".join(missing),
                "price_coverage_ratio": round(float(coverage_ratio), 4),
                "price_coverage_status": coverage_status,
                "explanation": explanation,
                **metrics,
            }
        )

    base = pd.DataFrame(rows)
    ranked = rank_backtest_results(base)
    meta = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "data_mode": "baseline_etf_sleeve_backtest",
        "prototype_baseline_backtest": True,
        "signal_conditioned_alpha_validation": False,
        "official_risk_decision_allowed": False,
        "price_source": price_source,
        **_price_panel_metadata(prices),
        "strategy_count": int(len(ranked)),
        "sufficient_coverage_count": int((ranked["price_coverage_status"] == "sufficient").sum()),
        "partial_coverage_count": int((ranked["price_coverage_status"] == "partial").sum()),
        "insufficient_coverage_count": int((ranked["price_coverage_status"] == "insufficient").sum()),
        "note": (
            "Baseline long-only equal-weight ETF sleeve comparison. "
            "Not production backtest, not WFO, and not a trade recommendation."
        ),
        "items": ranked.to_dict(orient="records"),
    }
    return ranked, meta


def _strategy_return_map(
    close_df: pd.DataFrame,
    strategies: pd.DataFrame,
) -> tuple[dict[str, pd.Series], dict[str, dict[str, Any]]]:
    """Build return series plus coverage audit details for every strategy."""
    returns_by_strategy: dict[str, pd.Series] = {}
    coverage_by_strategy: dict[str, dict[str, Any]] = {}
    investable = _investable_tickers()
    for _, strategy in strategies.iterrows():
        strategy_id = str(strategy["strategy_id"])
        tickers = parse_target_etfs(strategy["target_etfs"])
        returns, available, missing, coverage_ratio, coverage_status = build_strategy_returns(
            close_df,
            tickers,
            investable,
        )
        returns_by_strategy[strategy_id] = returns
        coverage_by_strategy[strategy_id] = {
            "category": str(strategy["category"]),
            "target_etfs": ";".join(tickers),
            "available_price_etfs": ";".join(available),
            "missing_price_etfs": ";".join(missing),
            "price_coverage_ratio": round(float(coverage_ratio), 4),
            "price_coverage_status": coverage_status,
        }
    return returns_by_strategy, coverage_by_strategy


def _make_walk_forward_windows(
    dates: pd.DatetimeIndex,
    *,
    train_years: int,
    test_months: int,
    step_months: int,
) -> list[dict[str, pd.Timestamp]]:
    """Create rolling train/test windows with no overlap leakage."""
    if len(dates) == 0:
        return []
    start = pd.Timestamp(dates.min()).normalize()
    end = pd.Timestamp(dates.max()).normalize()
    train_offset = pd.DateOffset(years=train_years)
    test_offset = pd.DateOffset(months=test_months)
    step_offset = pd.DateOffset(months=step_months)

    test_start = (start + train_offset).normalize()
    windows: list[dict[str, pd.Timestamp]] = []
    while test_start <= end:
        train_start = (test_start - train_offset).normalize()
        train_end = (test_start - pd.Timedelta(days=1)).normalize()
        test_end = min((test_start + test_offset - pd.Timedelta(days=1)).normalize(), end)
        if test_end >= test_start:
            windows.append(
                {
                    "train_start": train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                }
            )
        test_start = (test_start + step_offset).normalize()
    return windows


def _window_schedule_rows(windows: list[dict[str, pd.Timestamp]]) -> list[dict[str, Any]]:
    """Compact one-row-per-window schedule for dashboard audit."""
    return [
        {
            "window_number": index,
            "train_start": window["train_start"].date().isoformat(),
            "train_end": window["train_end"].date().isoformat(),
            "test_start": window["test_start"].date().isoformat(),
            "test_end": window["test_end"].date().isoformat(),
        }
        for index, window in enumerate(windows, start=1)
    ]


def _slice_returns(
    returns: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    if returns.empty:
        return returns
    idx = pd.to_datetime(returns.index)
    sliced = returns[(idx >= start) & (idx <= end)].dropna()
    sliced.index = pd.to_datetime(sliced.index)
    return sliced


def walk_forward_evaluate_strategies(
    price_path: Path | str | None = None,
    *,
    train_years: int = 5,
    test_months: int = 12,
    step_months: int = 3,
    top_n: int = 5,
    min_train_observations: int = 504,
    min_test_observations: int = 63,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Rolling out-of-sample evaluation for strategy sleeves.

    Each window ranks strategies on the training period only, then reports
    performance in the following test period. This is WFO-style evaluation, not
    proof of alpha and not automatic strategy switching.
    """
    strategies = load_strategy_library()
    prices, price_source = load_strategy_price_panel(price_path=price_path)
    close_df = _pivot_close_prices(prices)
    returns_by_strategy, coverage_by_strategy = _strategy_return_map(close_df, strategies)
    all_dates = pd.DatetimeIndex(close_df.index)
    windows = _make_walk_forward_windows(
        all_dates,
        train_years=train_years,
        test_months=test_months,
        step_months=step_months,
    )
    window_schedule = _window_schedule_rows(windows)

    window_rows: list[dict[str, Any]] = []
    for window_number, window in enumerate(windows, start=1):
        train_rows: list[dict[str, Any]] = []
        test_returns: dict[str, pd.Series] = {}
        for strategy_id, returns in returns_by_strategy.items():
            train = _slice_returns(returns, window["train_start"], window["train_end"])
            test = _slice_returns(returns, window["test_start"], window["test_end"])
            if len(train) < min_train_observations or len(test) < min_test_observations:
                continue
            train_metrics = compute_backtest_metrics(train, pd.Series(dtype=float))
            train_rows.append({"strategy_id": strategy_id, **train_metrics})
            test_returns[strategy_id] = test

        if len(train_rows) < max(2, min(top_n, len(strategies))):
            continue

        train_df = pd.DataFrame(train_rows)
        train_df["train_score"] = _score_frame_for_ranking(train_df)
        train_df["train_rank"] = train_df["train_score"].rank(
            method="min",
            ascending=False,
        ).astype(int)
        selected_ids = set(
            train_df.loc[train_df["train_rank"] <= top_n, "strategy_id"].astype(str)
        )

        for _, train_row in train_df.iterrows():
            strategy_id = str(train_row["strategy_id"])
            test = test_returns[strategy_id]
            test_metrics = compute_backtest_metrics(test, pd.Series(dtype=float))
            window_rows.append(
                {
                    "window_number": window_number,
                    "strategy_id": strategy_id,
                    "train_start": window["train_start"].date().isoformat(),
                    "train_end": window["train_end"].date().isoformat(),
                    "test_start": window["test_start"].date().isoformat(),
                    "test_end": window["test_end"].date().isoformat(),
                    "train_rank": int(train_row["train_rank"]),
                    "train_score": round(float(train_row["train_score"]), 4),
                    "selected_top_n": strategy_id in selected_ids,
                    "oos_total_return": test_metrics["total_return"],
                    "oos_sharpe": test_metrics["sharpe_proxy"],
                    "oos_max_drawdown": test_metrics["max_drawdown"],
                    "oos_monthly_win_rate": test_metrics["win_rate_monthly"],
                    "oos_observation_count": test_metrics["observation_count"],
                }
            )

    if not window_rows:
        empty = pd.DataFrame(columns=WFO_RESULT_COLUMNS)
        meta = {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "data_mode": "walk_forward_strategy_evaluation",
            "walk_forward_optimization": True,
            "signal_conditioned_alpha_validation": False,
            "official_risk_decision_allowed": False,
            "price_source": price_source,
            **_price_panel_metadata(prices),
            "strategy_count": int(len(strategies)),
            "window_count": 0,
            "train_years": train_years,
            "test_months": test_months,
            "step_months": step_months,
            "top_n": top_n,
            "min_train_observations": min_train_observations,
            "min_test_observations": min_test_observations,
            "rolling_window_summary": {
                "train": f"{train_years} years",
                "test": f"{test_months} months",
                "step": f"{step_months} months",
                "no_lookahead_rule": "each train_end is before test_start; test returns are never used for train ranking",
            },
            "note": (
                "No WFO windows were available. Fetch longer history, e.g. "
                "python scripts/fetch_openbb_prices.py --years 10."
            ),
            "items": [],
            "windows": [],
            "window_schedule": [],
        }
        return empty, meta

    window_df = pd.DataFrame(window_rows)
    valid_window_schedule = (
        window_df[
            ["window_number", "train_start", "train_end", "test_start", "test_end"]
        ]
        .drop_duplicates()
        .sort_values("window_number")
        .to_dict(orient="records")
    )
    summary_rows: list[dict[str, Any]] = []
    for _, strategy in strategies.iterrows():
        strategy_id = str(strategy["strategy_id"])
        rows = window_df[window_df["strategy_id"] == strategy_id].copy()
        coverage = coverage_by_strategy[strategy_id]
        if rows.empty:
            summary_rows.append(
                {
                    **coverage,
                    "strategy_id": strategy_id,
                    "window_count": 0,
                    "selected_top5_window_count": 0,
                    "train_top5_hit_rate": 0.0,
                    "oos_avg_total_return": None,
                    "oos_avg_sharpe": None,
                    "oos_avg_max_drawdown": None,
                    "oos_avg_monthly_win_rate": None,
                    "oos_positive_window_rate": None,
                    "selected_oos_avg_total_return": None,
                    "selected_oos_positive_window_rate": None,
                    "first_test_start": None,
                    "last_test_end": None,
                    "explanation": "No valid WFO windows for this strategy.",
                }
            )
            continue
        selected = rows[rows["selected_top_n"]].copy()
        total_values = pd.to_numeric(rows["oos_total_return"], errors="coerce")
        selected_total_values = pd.to_numeric(selected["oos_total_return"], errors="coerce")
        summary_rows.append(
            {
                **coverage,
                "strategy_id": strategy_id,
                "window_count": int(len(rows)),
                "selected_top5_window_count": int(len(selected)),
                "train_top5_hit_rate": round(float(len(selected) / len(rows)), 4),
                "oos_avg_total_return": float(total_values.mean()),
                "oos_avg_sharpe": float(pd.to_numeric(rows["oos_sharpe"], errors="coerce").mean()),
                "oos_avg_max_drawdown": float(
                    pd.to_numeric(rows["oos_max_drawdown"], errors="coerce").mean()
                ),
                "oos_avg_monthly_win_rate": float(
                    pd.to_numeric(rows["oos_monthly_win_rate"], errors="coerce").mean()
                ),
                "oos_positive_window_rate": float((total_values > 0).mean()),
                "selected_oos_avg_total_return": (
                    float(selected_total_values.mean()) if not selected.empty else None
                ),
                "selected_oos_positive_window_rate": (
                    float((selected_total_values > 0).mean()) if not selected.empty else None
                ),
                "first_test_start": str(rows["test_start"].min()),
                "last_test_end": str(rows["test_end"].max()),
                "explanation": (
                    "WFO-style rolling evaluation: train-window rank uses only past data; "
                    "reported OOS metrics use the following test window."
                ),
            }
        )

    summary = pd.DataFrame(summary_rows)
    summary["wfo_score"] = (
        0.25 * _percentile_scores(summary["oos_avg_total_return"], higher_is_better=True)
        + 0.25 * _percentile_scores(summary["oos_avg_sharpe"], higher_is_better=True)
        + 0.20 * _percentile_scores(summary["oos_avg_max_drawdown"], higher_is_better=True)
        + 0.15 * _percentile_scores(summary["oos_positive_window_rate"], higher_is_better=True)
        + 0.15 * _percentile_scores(summary["train_top5_hit_rate"], higher_is_better=True)
    )
    no_windows = summary["window_count"].astype(int) == 0
    summary.loc[no_windows, "wfo_score"] = 0.0
    summary["wfo_status"] = "walk_forward_evaluated"
    summary.loc[no_windows, "wfo_status"] = "no_valid_windows"
    summary.loc[summary["price_coverage_ratio"].astype(float) < 0.50, "wfo_status"] = (
        "insufficient_price_coverage"
    )
    summary = summary.sort_values(
        ["wfo_score", "train_top5_hit_rate", "price_coverage_ratio"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    summary.insert(0, "wfo_rank", summary.index + 1)
    summary["wfo_score"] = summary["wfo_score"].round(4)
    output = summary[WFO_RESULT_COLUMNS]
    meta = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "data_mode": "walk_forward_strategy_evaluation",
        "walk_forward_optimization": True,
        "signal_conditioned_alpha_validation": False,
        "official_risk_decision_allowed": False,
        "price_source": price_source,
        **_price_panel_metadata(prices),
        "strategy_count": int(len(output)),
        "window_count": int(window_df["window_number"].nunique()),
        "train_years": train_years,
        "test_months": test_months,
        "step_months": step_months,
        "top_n": top_n,
        "min_train_observations": min_train_observations,
        "min_test_observations": min_test_observations,
        "rolling_window_summary": {
            "train": f"{train_years} years",
            "test": f"{test_months} months",
            "step": f"{step_months} months",
            "no_lookahead_rule": "each train_end is before test_start; test returns are never used for train ranking",
        },
        "note": (
            "Walk-forward style rolling out-of-sample evaluation of ETF sleeves. "
            "This ranks fixed candidate sleeves using training-window evidence, then "
            "evaluates the next test window. WFO score blends OOS return, OOS Sharpe, "
            "OOS drawdown, positive OOS window rate, and train-window top-5 stability. "
            "It is not signal-conditioned alpha proof and not a trade recommendation."
        ),
        "items": _json_safe(output.to_dict(orient="records")),
        "windows": _json_safe(window_df.to_dict(orient="records")),
        "window_schedule": _json_safe(valid_window_schedule),
    }
    return output, meta


def build_walk_forward_snapshot(
    price_path: Path | str | None = None,
    *,
    train_years: int = 5,
    test_months: int = 12,
    step_months: int = 3,
    top_n: int = 5,
) -> dict[str, Any]:
    """JSON-serializable walk-forward strategy evaluation snapshot."""
    _, meta = walk_forward_evaluate_strategies(
        price_path=price_path,
        train_years=train_years,
        test_months=test_months,
        step_months=step_months,
        top_n=top_n,
    )
    return _json_safe(meta)


def build_backtest_snapshot(price_path: Path | str | None = None) -> dict[str, Any]:
    """JSON-serializable baseline strategy backtest snapshot."""
    _, meta = backtest_all_strategies(price_path=price_path)
    return _json_safe(meta)
