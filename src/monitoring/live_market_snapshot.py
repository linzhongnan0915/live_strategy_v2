"""
Read-only Bloomberg-style market monitor snapshot from OpenBB price panels.

Uses raw file for latest observations and processed aligned file for official EOD date only.
Does not drive rule engine, escalation, or official risk decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.config_loader import PROJECT_ROOT, load_etf_universe, load_holdings
from src.data.price_panel_quality import validate_official_eod_panel
from src.portfolio.metrics_builder import PRICE_COLUMNS, REQUIRED_PRICE_TICKERS

DATA_MODE = "openbb_yfinance_market_monitor"
OFFICIAL_EOD_SOURCE = "openbb_yfinance"
MONITOR_NOTE = (
    "Market monitor snapshot for situational awareness only. "
    "Latest raw observations may be asynchronous across tickers. "
    "Do not use for official EOD risk triggers or strategy decisions."
)
MONITOR_ONLY_META = {
    "asset_class": "monitor_only",
    "risk_bucket": "monitor_only",
    "target_weight": 0.0,
}


def _normalize_panel(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    work["ticker"] = work["ticker"].astype(str)
    work["source"] = work["source"].astype(str)
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    return work


def _read_price_panel(path: Path, label: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if list(df.columns) != PRICE_COLUMNS:
        raise ValueError(
            f"{label} price columns must be {PRICE_COLUMNS}; got {list(df.columns)}"
        )
    return df


def _validate_raw_monitor_panel(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("raw market monitor panel is empty")
    if not (df["source"].astype(str) == OFFICIAL_EOD_SOURCE).all():
        bad = sorted(df["source"].astype(str).unique().tolist())
        raise ValueError(
            f"raw market monitor source must be {OFFICIAL_EOD_SOURCE} for all rows; got {bad}"
        )
    close_numeric = pd.to_numeric(df["close"], errors="coerce")
    if df["close"].isna().any():
        raise ValueError("raw market monitor panel contains null close values")
    if close_numeric.isna().any():
        raise ValueError("raw market monitor panel contains non-numeric close values")


def _load_holdings_metadata(holdings_path: Path | str | None) -> pd.DataFrame:
    if holdings_path is None:
        return load_holdings()
    path = Path(holdings_path)
    if not path.exists():
        raise FileNotFoundError(f"holdings file not found: {path}")
    return pd.read_csv(path)


def _default_monitor_tickers() -> list[str]:
    """Use the ETF universe for display, excluding high-risk prototype instruments."""
    universe = load_etf_universe()
    tickers = [
        str(row["ticker"]).strip().upper()
        for _, row in universe.iterrows()
        if str(row.get("implementation_role", "")).strip() != "high_risk_prototype"
    ]
    return list(dict.fromkeys(tickers))


def _official_eod_date(processed_df: pd.DataFrame) -> str:
    dates = _normalize_panel(processed_df)["date"]
    if dates.empty:
        raise ValueError("processed panel has no dates; cannot determine official_eod_date")
    return str(dates.max())


def _timing_status(latest_date: str | None, official_eod_date: str) -> str:
    if latest_date is None:
        return "stale_vs_official_eod"
    if latest_date == official_eod_date:
        return "official_eod_aligned"
    if latest_date > official_eod_date:
        return "newer_than_official_eod"
    return "stale_vs_official_eod"


def _stale_days(latest_date: str | None, official_eod_date: str) -> int:
    if latest_date is None or latest_date >= official_eod_date:
        return 0
    latest = pd.Timestamp(latest_date)
    official = pd.Timestamp(official_eod_date)
    return int((official - latest).days)


def _display_warning(
    ticker: str,
    timing_status: str,
    stale_days: int,
    has_return: bool,
    observation_count: int,
) -> str:
    if observation_count < 2:
        return f"{ticker}: insufficient price history for return (fewer than 2 observations)."
    if not has_return:
        return f"{ticker}: latest return unavailable."
    if timing_status == "newer_than_official_eod":
        return (
            f"{ticker}: latest observation is newer than official EOD; "
            "watchlist context only, not an official risk trigger."
        )
    if timing_status == "stale_vs_official_eod" and stale_days > 0:
        return (
            f"{ticker}: latest observation is {stale_days} day(s) behind official EOD; "
            "verify calendar alignment before acting."
        )
    return ""


def _build_ticker_item(
    ticker: str,
    raw_df: pd.DataFrame,
    official_eod_date: str,
    holdings_meta: dict[str, dict[str, Any]],
    stale_days_threshold: int,
) -> dict[str, Any]:
    meta = holdings_meta.get(ticker, MONITOR_ONLY_META.copy())
    sub = raw_df[raw_df["ticker"] == ticker].dropna(subset=["close"]).sort_values("date")
    observation_count = len(sub)

    latest_date: str | None = None
    latest_close: float | None = None
    previous_date: str | None = None
    previous_close: float | None = None
    source: str | None = None
    latest_return: float | None = None
    latest_return_pct: float | None = None

    if observation_count >= 1:
        latest_row = sub.iloc[-1]
        latest_date = str(latest_row["date"])
        latest_close = float(latest_row["close"])
        source = str(latest_row["source"])
    if observation_count >= 2:
        prev_row = sub.iloc[-2]
        previous_date = str(prev_row["date"])
        previous_close = float(prev_row["close"])
        if previous_close and previous_close != 0:
            latest_return = latest_close / previous_close - 1.0  # type: ignore[operator]
            latest_return_pct = latest_return * 100.0

    timing = _timing_status(latest_date, official_eod_date)
    stale_days = _stale_days(latest_date, official_eod_date)
    is_stale = stale_days >= stale_days_threshold
    warning = _display_warning(
        ticker,
        timing,
        stale_days,
        latest_return is not None,
        observation_count,
    )

    return {
        "ticker": ticker,
        "asset_class": meta["asset_class"],
        "risk_bucket": meta["risk_bucket"],
        "target_weight": float(meta["target_weight"]),
        "source": source,
        "latest_date": latest_date,
        "latest_close": latest_close,
        "previous_date": previous_date,
        "previous_close": previous_close,
        "latest_return": latest_return,
        "latest_return_pct": latest_return_pct,
        "official_eod_date": official_eod_date,
        "timing_status": timing,
        "stale_days": stale_days,
        "is_stale": is_stale,
        "display_warning": warning,
    }


def build_market_monitor_snapshot(
    raw_price_path: Path | str,
    processed_price_path: Path | str,
    holdings_path: Path | str | None = None,
    stale_days_threshold: int = 3,
    monitor_tickers: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build read-only market monitor snapshot from raw latest obs and processed EOD date.

    Inputs:
    - raw_price_path: OpenBB raw CSV (latest available per ticker).
    - processed_price_path: aligned official EOD panel (date anchor only).
    """
    raw_p = Path(raw_price_path)
    proc_p = Path(processed_price_path)
    if not raw_p.exists():
        raise FileNotFoundError(
            f"raw OpenBB price file not found: {raw_p}. "
            "Run python scripts/fetch_openbb_prices.py first."
        )
    if not proc_p.exists():
        raise FileNotFoundError(
            f"processed aligned price file not found: {proc_p}. "
            "Run python scripts/process_openbb_prices.py first."
        )

    raw_input = _read_price_panel(raw_p, "raw")
    processed_input = _read_price_panel(proc_p, "processed")
    _validate_raw_monitor_panel(raw_input)
    validate_official_eod_panel(
        processed_input,
        REQUIRED_PRICE_TICKERS,
        OFFICIAL_EOD_SOURCE,
    )
    raw_df = _normalize_panel(raw_input)
    processed_df = _normalize_panel(processed_input)

    official_eod = _official_eod_date(processed_df)
    tickers = list(monitor_tickers or _default_monitor_tickers())

    holdings_df = _load_holdings_metadata(holdings_path)
    holdings_meta: dict[str, dict[str, Any]] = {}
    for _, row in holdings_df.iterrows():
        t = str(row["ticker"])
        holdings_meta[t] = {
            "asset_class": str(row.get("asset_class", MONITOR_ONLY_META["asset_class"])),
            "risk_bucket": str(row.get("risk_bucket", MONITOR_ONLY_META["risk_bucket"])),
            "target_weight": float(row.get("target_weight", 0.0)),
        }

    items = [
        _build_ticker_item(t, raw_df, official_eod, holdings_meta, stale_days_threshold)
        for t in tickers
    ]

    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "raw_price_path": str(raw_p.resolve()),
        "processed_price_path": str(proc_p.resolve()),
        "official_eod_date": official_eod,
        "row_count": len(items),
        "ticker_count": len(items),
        "data_mode": DATA_MODE,
        "official_risk_decision_allowed": False,
        "note": MONITOR_NOTE,
        "items": items,
    }


def snapshot_to_jsonable(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Convert snapshot values to plain JSON types."""
    out = dict(snapshot)
    json_items = []
    for item in snapshot["items"]:
        row = dict(item)
        for key, value in row.items():
            if isinstance(value, (pd.Timestamp,)):
                row[key] = value.isoformat()
        json_items.append(row)
    out["items"] = json_items
    return out


DEFAULT_RAW_PATH = PROJECT_ROOT / "data" / "raw" / "openbb_price_history.csv"
DEFAULT_PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
