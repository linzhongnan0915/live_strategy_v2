"""Tests for portfolio metrics builder."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.portfolio.metrics_builder import (
    ALLOWED_PRICE_SOURCES,
    COMPUTED_DATA_SOURCE,
    DEFAULT_PRICE_PATH,
    EXPECTED_PRICE_SOURCE,
    REQUIRED_PRICE_TICKERS,
    build_metrics_snapshot,
    compute_drawdown,
    compute_historical_var_ratio,
    compute_portfolio_returns,
    compute_relative_return,
    compute_simple_return,
    compute_vix_change,
    compute_vix_level,
    derive_computed_data_source,
    load_price_history,
    pivot_close_prices,
    validate_price_history,
)
from src.regime.rule_engine import run_rule_engine

COMPUTED_SNAPSHOT = (
    Path(__file__).resolve().parents[1] / "data" / "samples" / "computed_metrics_snapshot.json"
)

REQUIRED_METRIC_KEYS = [
    "VIX level",
    "VIX change",
    "SPY return",
    "QQQ return",
    "IWM return",
    "TLT return",
    "IEF return",
    "SHY return",
    "HYG return",
    "LQD return",
    "TIP return",
    "GLD return",
    "USO return",
    "UUP return",
    "HYG vs LQD relative return",
    "SPY drawdown",
    "portfolio drawdown",
    "portfolio VaR",
    "headline severity",
    "cross-asset confirmation count",
    "strategy return deviation",
]


def test_sample_price_history_loads_and_source_tag():
    df = load_price_history()
    assert len(df) > 0
    assert (df["source"] == EXPECTED_PRICE_SOURCE).all()


def test_required_tickers_exist():
    df = load_price_history()
    present = set(df["ticker"].unique())
    for ticker in REQUIRED_PRICE_TICKERS:
        assert ticker in present


def test_vix_exists_in_sample_price_history():
    df = load_price_history()
    vix = df[df["ticker"] == "VIX"]
    assert len(vix) == df["date"].nunique()
    assert (vix["source"] == "sample_synthetic").all()


def test_pivot_close_prices_shape():
    df = load_price_history()
    wide = pivot_close_prices(df)
    assert wide.shape[0] >= 30
    assert wide.shape[1] == len(REQUIRED_PRICE_TICKERS)
    assert set(REQUIRED_PRICE_TICKERS).issubset(set(wide.columns))
    assert "VIX" in wide.columns


def test_compute_simple_return_toy_series():
    dates = pd.bdate_range("2026-01-01", periods=6)
    close_df = pd.DataFrame({"AAA": [100, 102, 104, 103, 105, 110]}, index=dates)
    ret = compute_simple_return(close_df, "AAA", lookback=5, as_of_date=dates[-1])
    assert ret == pytest.approx(110 / 100 - 1.0)


def test_compute_drawdown_toy_series():
    dates = pd.bdate_range("2026-01-01", periods=6)
    close_df = pd.DataFrame({"AAA": [100, 110, 115, 90, 95, 92]}, index=dates)
    dd = compute_drawdown(close_df, "AAA", lookback=5, as_of_date=dates[-1])
    assert dd < 0
    assert dd == pytest.approx(92 / 115 - 1.0)


def test_compute_relative_return_toy():
    dates = pd.bdate_range("2026-01-01", periods=6)
    close_df = pd.DataFrame(
        {"HYG": [100, 99, 98, 97, 96, 95], "LQD": [100, 100, 101, 101, 102, 102]},
        index=dates,
    )
    rel = compute_relative_return(close_df, "HYG", "LQD", 5, dates[-1])
    hyg_ret = 95 / 100 - 1
    lqd_ret = 102 / 100 - 1
    assert rel == pytest.approx(hyg_ret - lqd_ret)


def test_portfolio_returns_uses_weights():
    from src.data.config_loader import load_holdings

    wide = pivot_close_prices(load_price_history())
    holdings = load_holdings()
    port = compute_portfolio_returns(wide, holdings)
    assert not port.empty
    assert port.name == "portfolio_return"
    assert len(port) == len(wide) - 1


def test_portfolio_returns_first_date_after_first_price_date():
    from src.data.config_loader import load_holdings

    wide = pivot_close_prices(load_price_history())
    port = compute_portfolio_returns(wide, load_holdings())
    assert port.index.min() > wide.index.min()


def test_portfolio_returns_no_artificial_zero_first_row():
    from src.data.config_loader import load_holdings

    wide = pivot_close_prices(load_price_history())
    port = compute_portfolio_returns(wide, load_holdings())
    first_price_date = wide.index.min()
    assert first_price_date not in port.index
    if len(port) > 0:
        assert port.iloc[0] != 0.0 or port.index[0] != first_price_date


def test_historical_var_ratio_non_negative():
    from src.data.config_loader import load_holdings

    wide = pivot_close_prices(load_price_history())
    port = compute_portfolio_returns(wide, load_holdings())
    ratio = compute_historical_var_ratio(port, lookback=20)
    assert isinstance(ratio, float)
    assert ratio >= 0.0


def test_build_metrics_snapshot_required_keys():
    snapshot = build_metrics_snapshot()
    for key in REQUIRED_METRIC_KEYS:
        assert key in snapshot["metrics"]


def test_build_metrics_snapshot_includes_tip_return():
    snapshot = build_metrics_snapshot()
    assert isinstance(snapshot["metrics"]["TIP return"], float)


def test_build_metrics_snapshot_data_source():
    snapshot = build_metrics_snapshot()
    assert snapshot["data_source"] == COMPUTED_DATA_SOURCE


def test_build_metrics_snapshot_vix_from_prices():
    wide = pivot_close_prices(load_price_history())
    as_of = wide.index.max()
    snapshot = build_metrics_snapshot()
    assert snapshot["metrics"]["VIX level"] == pytest.approx(float(wide.loc[as_of, "VIX"]))
    expected_change = float(wide.loc[as_of, "VIX"] - wide.iloc[-2]["VIX"])
    assert snapshot["metrics"]["VIX change"] == pytest.approx(expected_change)
    assert compute_vix_level(wide, as_of) == snapshot["metrics"]["VIX level"]
    assert compute_vix_change(wide, as_of) == pytest.approx(expected_change)


def test_vix_not_old_placeholder_constants():
    snapshot = build_metrics_snapshot()
    # Sample VIX series is designed with final level 24 and change 3.5, not 22/2.
    assert snapshot["metrics"]["VIX level"] == pytest.approx(24.0)
    assert snapshot["metrics"]["VIX change"] == pytest.approx(3.5)


def test_vix_no_look_ahead():
    wide = pivot_close_prices(load_price_history())
    dates = wide.index.sort_values()
    early = dates[10]
    late = dates[-1]
    assert compute_vix_level(wide, early) != compute_vix_level(wide, late)


def test_no_look_ahead_build_metrics_differ_by_as_of_date():
    wide = pivot_close_prices(load_price_history())
    dates = wide.index.sort_values()
    early = dates[21].strftime("%Y-%m-%d")
    late = dates[-1].strftime("%Y-%m-%d")
    snap_early = build_metrics_snapshot(as_of_date=early)
    snap_late = build_metrics_snapshot(as_of_date=late)
    assert snap_early["metrics"]["SPY return"] != snap_late["metrics"]["SPY return"]


def test_computed_snapshot_runs_rule_engine(tmp_path):
    snapshot = build_metrics_snapshot()
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    result = run_rule_engine(metrics_path=path)
    assert "escalation_level" in result["alerts"].columns


def test_price_history_date_range():
    df = load_price_history()
    assert df["date"].min().strftime("%Y-%m-%d") == "2026-03-03"
    assert df["date"].max().strftime("%Y-%m-%d") == "2026-04-14"
    assert len(df) == 31 * len(REQUIRED_PRICE_TICKERS)
    assert df["date"].nunique() == 31


def _sample_prices_with_source(source: str) -> pd.DataFrame:
    df = pd.read_csv(DEFAULT_PRICE_PATH)
    df["source"] = source
    return df


def test_openbb_yfinance_loads_when_expected(tmp_path):
    path = tmp_path / "openbb_prices.csv"
    _sample_prices_with_source("openbb_yfinance").to_csv(path, index=False)
    df = load_price_history(path, expected_source="openbb_yfinance")
    assert (df["source"] == "openbb_yfinance").all()
    snapshot = build_metrics_snapshot(path, expected_source="openbb_yfinance")
    assert snapshot["data_source"] == "openbb_yfinance_computed_from_prices"


def test_openbb_yfinance_rejected_by_default(tmp_path):
    path = tmp_path / "openbb_prices.csv"
    _sample_prices_with_source("openbb_yfinance").to_csv(path, index=False)
    with pytest.raises(ValueError, match="sample_synthetic"):
        load_price_history(path)


def test_unknown_source_rejected_even_when_expected_source_none():
    df = _sample_prices_with_source("vendor_xyz")
    with pytest.raises(ValueError, match="unknown"):
        validate_price_history(df, expected_source=None)


def test_expected_source_none_allows_allowed_sources_only():
    sample_df = _sample_prices_with_source("sample_synthetic")
    validate_price_history(sample_df, expected_source=None)
    openbb_df = _sample_prices_with_source("openbb_yfinance")
    validate_price_history(openbb_df, expected_source=None)
    assert ALLOWED_PRICE_SOURCES == {"sample_synthetic", "openbb_yfinance"}


def test_derive_computed_data_source_sample():
    df = _sample_prices_with_source("sample_synthetic")
    assert derive_computed_data_source(df) == COMPUTED_DATA_SOURCE


def test_derive_computed_data_source_openbb():
    df = _sample_prices_with_source("openbb_yfinance")
    assert derive_computed_data_source(df) == "openbb_yfinance_computed_from_prices"


def test_derive_computed_data_source_mixed_allowed():
    df = _sample_prices_with_source("sample_synthetic")
    df.loc[df.index % 2 == 0, "source"] = "openbb_yfinance"
    assert derive_computed_data_source(df) == "mixed_allowed_sources_computed_from_prices"
