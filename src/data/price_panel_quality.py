"""
Price panel data quality and timing governance helpers.

Separates raw feeds, processed official EOD panels, and future live monitor inputs.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.portfolio.metrics_builder import PRICE_COLUMNS

READINESS_OFFICIAL_EOD = "official_eod_ready"
READINESS_RAW_INCOMPLETE = "raw_incomplete_needs_processing"
READINESS_INVALID_MISSING = "invalid_missing_tickers"
READINESS_INVALID_DUPLICATES = "invalid_duplicates"
READINESS_INVALID_EMPTY = "invalid_empty"
READINESS_INVALID_SCHEMA = "invalid_schema"
READINESS_INVALID_CLOSE = "invalid_close_values"


def _normalize_panel(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    work["ticker"] = work["ticker"].astype(str)
    work["source"] = work["source"].astype(str)
    return work


def _tickers_missing_on_date(group: pd.DataFrame, required_tickers: list[str]) -> list[str]:
    missing: list[str] = []
    for ticker in required_tickers:
        sub = group[group["ticker"] == ticker]
        numeric_close = pd.to_numeric(sub["close"], errors="coerce")
        if numeric_close.notna().sum() != 1:
            missing.append(ticker)
    return missing


def _empty_summary(
    df: pd.DataFrame,
    required_tickers: list[str],
    schema_valid: bool,
    schema_error: str | None = None,
) -> dict[str, Any]:
    source_values: list[str] = []
    if "source" in df.columns and not df.empty:
        source_values = sorted(df["source"].astype(str).unique().tolist())
    return {
        "schema_valid": schema_valid,
        "schema_error": schema_error,
        "row_count": len(df),
        "date_count": 0,
        "ticker_count": 0,
        "date_min": None,
        "date_max": None,
        "tickers_present": [],
        "missing_required_tickers": list(required_tickers),
        "source_values": source_values,
        "duplicate_date_ticker_count": 0,
        "rows_per_date_min": 0,
        "rows_per_date_max": 0,
        "complete_date_count": 0,
        "incomplete_date_count": 0,
        "incomplete_dates": [],
        "close_null_count": 0,
        "close_non_numeric_count": 0,
    }


def summarize_price_panel(
    df: pd.DataFrame,
    required_tickers: list[str],
) -> dict[str, Any]:
    """Summarize long-format price panel completeness and source tags."""
    tickers = list(required_tickers)
    if df.empty:
        return _empty_summary(df, tickers, schema_valid=list(df.columns) == PRICE_COLUMNS)
    if list(df.columns) != PRICE_COLUMNS:
        return _empty_summary(
            df,
            tickers,
            schema_valid=False,
            schema_error=f"price panel columns must be {PRICE_COLUMNS}; got {list(df.columns)}",
        )

    work = _normalize_panel(df)
    present = sorted(work["ticker"].unique().tolist())
    missing_required = [t for t in tickers if t not in present]
    dates = sorted(work["date"].unique().tolist())
    close_numeric = pd.to_numeric(work["close"], errors="coerce")
    close_null_count = int(work["close"].isna().sum())
    close_non_numeric_count = int((close_numeric.isna() & work["close"].notna()).sum())

    dup_mask = work.groupby(["date", "ticker"]).size() > 1
    duplicate_date_ticker_count = int(dup_mask.sum())

    rows_per_date = work.groupby("date").size()
    incomplete_dates: list[dict[str, Any]] = []
    complete_date_count = 0
    for date in dates:
        group = work[work["date"] == date]
        missing_on_date = _tickers_missing_on_date(group, tickers)
        if missing_on_date:
            incomplete_dates.append({"date": date, "missing_tickers": missing_on_date})
        else:
            complete_date_count += 1

    return {
        "schema_valid": True,
        "schema_error": None,
        "row_count": len(work),
        "date_count": len(dates),
        "ticker_count": len(present),
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "tickers_present": present,
        "missing_required_tickers": missing_required,
        "source_values": sorted(work["source"].unique().tolist()),
        "duplicate_date_ticker_count": duplicate_date_ticker_count,
        "rows_per_date_min": int(rows_per_date.min()) if len(rows_per_date) else 0,
        "rows_per_date_max": int(rows_per_date.max()) if len(rows_per_date) else 0,
        "complete_date_count": complete_date_count,
        "incomplete_date_count": len(incomplete_dates),
        "incomplete_dates": incomplete_dates,
        "close_null_count": close_null_count,
        "close_non_numeric_count": close_non_numeric_count,
    }


def classify_panel_readiness(summary: dict[str, Any]) -> str:
    """Classify whether a panel is official EOD ready or needs processing/fixes."""
    if summary.get("row_count", 0) == 0:
        return READINESS_INVALID_EMPTY
    if summary.get("schema_valid") is False:
        return READINESS_INVALID_SCHEMA
    if summary.get("date_count", 0) == 0:
        return READINESS_INVALID_EMPTY
    if summary.get("missing_required_tickers"):
        return READINESS_INVALID_MISSING
    if summary.get("duplicate_date_ticker_count", 0) > 0:
        return READINESS_INVALID_DUPLICATES
    if summary.get("close_null_count", 0) > 0 or summary.get("close_non_numeric_count", 0) > 0:
        return READINESS_INVALID_CLOSE
    if summary.get("incomplete_date_count", 0) > 0:
        return READINESS_RAW_INCOMPLETE
    if summary.get("complete_date_count", 0) == summary.get("date_count", 0):
        return READINESS_OFFICIAL_EOD
    return READINESS_INVALID_EMPTY


def validate_official_eod_panel(
    df: pd.DataFrame,
    required_tickers: list[str],
    expected_source: str,
) -> None:
    """
    Validate panel for official close-of-market risk metrics.

    Raises ValueError on any governance violation. Not for live overnight monitors.
    """
    if list(df.columns) != PRICE_COLUMNS:
        raise ValueError(f"price panel columns must be {PRICE_COLUMNS}; got {list(df.columns)}")
    if df.empty:
        raise ValueError("official EOD panel is empty")

    work = _normalize_panel(df)
    tickers = list(required_tickers)

    if not (work["source"] == expected_source).all():
        bad = sorted(work["source"].unique().tolist())
        raise ValueError(
            f"official EOD panel source must be {expected_source} for all rows; got {bad}"
        )
    if work["close"].isna().any():
        raise ValueError("official EOD panel contains null close values")
    close_numeric = pd.to_numeric(work["close"], errors="coerce")
    if close_numeric.isna().any():
        raise ValueError("official EOD panel contains non-numeric close values")

    summary = summarize_price_panel(work, tickers)
    readiness = classify_panel_readiness(summary)
    if readiness == READINESS_INVALID_MISSING:
        raise ValueError(
            f"official EOD panel missing required tickers: {summary['missing_required_tickers']}"
        )
    if readiness == READINESS_INVALID_DUPLICATES:
        raise ValueError(
            f"official EOD panel has duplicate date/ticker rows: "
            f"{summary['duplicate_date_ticker_count']}"
        )
    if readiness == READINESS_RAW_INCOMPLETE:
        sample = summary["incomplete_dates"][:5]
        raise ValueError(
            f"official EOD panel has incomplete dates ({summary['incomplete_date_count']}); "
            f"examples: {sample}"
        )
    if readiness == READINESS_INVALID_CLOSE:
        raise ValueError(
            "official EOD panel has invalid close values: "
            f"null={summary['close_null_count']}, "
            f"non_numeric={summary['close_non_numeric_count']}"
        )
    if readiness != READINESS_OFFICIAL_EOD:
        raise ValueError(f"official EOD panel is not ready: {readiness}")

    expected_rows = summary["date_count"] * len(tickers)
    if summary["row_count"] != expected_rows:
        raise ValueError(
            f"official EOD panel must have one row per ticker per date; "
            f"expected {expected_rows} rows, got {summary['row_count']}"
        )
