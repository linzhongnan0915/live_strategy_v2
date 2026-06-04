"""Align raw OpenBB price history to a complete daily panel for metrics_builder."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.portfolio.metrics_builder import (
    PRICE_COLUMNS,
    REQUIRED_PRICE_TICKERS,
    build_metrics_snapshot,
)

DEFAULT_INPUT_PATH = _ROOT / "data" / "raw" / "openbb_price_history.csv"
DEFAULT_OUTPUT_PATH = _ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
OPENBB_SOURCE = "openbb_yfinance"
MISSING_INPUT_MESSAGE = (
    "Run python scripts/fetch_openbb_prices.py first"
)


def _tickers_missing_on_date(group: pd.DataFrame, required_tickers: list[str]) -> list[str]:
    """Tickers without exactly one non-null close on this date."""
    missing: list[str] = []
    for ticker in required_tickers:
        sub = group[group["ticker"].astype(str) == ticker]
        valid = sub["close"].notna().sum()
        if valid != 1:
            missing.append(ticker)
    return missing


def align_openbb_price_history(
    df: pd.DataFrame,
    required_tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Keep only dates where every required ticker has exactly one non-null close.

    No forward-fill; preserves openbb_yfinance source tag.
    """
    if list(df.columns) != PRICE_COLUMNS:
        raise ValueError(f"price history columns must be {PRICE_COLUMNS}; got {list(df.columns)}")
    if df.empty:
        raise ValueError("raw price history is empty")

    tickers = list(required_tickers or REQUIRED_PRICE_TICKERS)
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.strftime("%Y-%m-%d")
    work["ticker"] = work["ticker"].astype(str)

    present = set(work["ticker"].unique())
    missing_entirely = [t for t in tickers if t not in present]
    if missing_entirely:
        raise ValueError(
            f"required tickers missing entirely from raw file: {missing_entirely}"
        )

    work = work[work["ticker"].isin(tickers)].copy()
    raw_dates = sorted(work["date"].unique())

    complete_dates: list[str] = []
    dropped: list[tuple[str, list[str]]] = []
    for date in raw_dates:
        group = work[work["date"] == date]
        missing_on_date = _tickers_missing_on_date(group, tickers)
        if missing_on_date:
            dropped.append((date, missing_on_date))
        else:
            complete_dates.append(date)

    if not complete_dates:
        raise ValueError(
            "no complete trading dates remain after alignment; "
            "every date is missing at least one required ticker close"
        )

    aligned = work[work["date"].isin(complete_dates)].copy()
    aligned["source"] = OPENBB_SOURCE
    aligned = aligned.sort_values(["date", "ticker"]).reset_index(drop=True)

    stats: dict[str, Any] = {
        "required_ticker_count": len(tickers),
        "raw_row_count": len(work),
        "processed_row_count": len(aligned),
        "raw_date_count": len(raw_dates),
        "processed_date_count": len(complete_dates),
        "dropped_incomplete_date_count": len(dropped),
        "dropped_dates": dropped,
        "source_values": sorted(aligned["source"].astype(str).unique()),
    }
    return aligned, stats


def main(
    input_path: Path | None = None,
    output_path: Path | None = None,
) -> pd.DataFrame:
    in_path = input_path or DEFAULT_INPUT_PATH
    out_path = output_path or DEFAULT_OUTPUT_PATH

    if not in_path.exists():
        print(MISSING_INPUT_MESSAGE)
        raise SystemExit(1)

    raw = pd.read_csv(in_path)
    aligned, stats = align_openbb_price_history(raw)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(out_path, index=False)
    build_metrics_snapshot(price_path=out_path, expected_source="openbb_yfinance")

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    print(f"input: {in_path}")
    print(f"output: {out_path}")
    print(f"required_ticker_count: {stats['required_ticker_count']}")
    print(f"raw_row_count: {stats['raw_row_count']}")
    print(f"processed_row_count: {stats['processed_row_count']}")
    print(f"raw_date_count: {stats['raw_date_count']}")
    print(f"processed_date_count: {stats['processed_date_count']}")
    print(f"dropped_incomplete_date_count: {stats['dropped_incomplete_date_count']}")
    print("first_10_dropped_dates:")
    for date, missing in stats["dropped_dates"][:10]:
        print(f"  - {date}: missing or invalid {missing}")
    if stats["dropped_incomplete_date_count"] > 10:
        print(f"  ... and {stats['dropped_incomplete_date_count'] - 10} more")
    print(f"source_values: {', '.join(stats['source_values'])}")
    print(f"timestamp: {timestamp}")

    return aligned


if __name__ == "__main__":
    main()
