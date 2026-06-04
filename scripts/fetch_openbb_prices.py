"""
Fetch prototype market prices via OpenBB and write to data/raw/.

Does not modify data/samples unless --output is explicitly set there.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.external.openbb_client import (
    PRICE_HISTORY_COLUMNS,
    VIX_MAPPING_NOTE,
    fetch_openbb_price_history,
)
from src.data.config_loader import load_etf_universe
from src.portfolio.metrics_builder import REQUIRED_PRICE_TICKERS

DEFAULT_OUTPUT = _ROOT / "data" / "raw" / "openbb_price_history.csv"
DEFAULT_PROVIDER = "yfinance"
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_LOOKBACK_YEARS = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch OpenBB price history to data/raw/")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument(
        "--years",
        type=int,
        default=DEFAULT_LOOKBACK_YEARS,
        help=(
            "Lookback years when --start-date is omitted. "
            "Use 10 or 20 for long strategy research backtests."
        ),
    )
    parser.add_argument(
        "--universe",
        choices=["etf_universe", "required_metrics"],
        default="etf_universe",
        help=(
            "Ticker universe to fetch. etf_universe supports strategy research; "
            "required_metrics fetches the smaller metrics-builder set."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output CSV path (default: data/raw/openbb_price_history.csv)",
    )
    return parser.parse_args()


def _resolve_tickers(universe: str) -> list[str]:
    if universe == "required_metrics":
        return list(REQUIRED_PRICE_TICKERS)
    etfs = load_etf_universe()
    tickers = [
        str(row["ticker"]).strip().upper()
        for _, row in etfs.iterrows()
        if str(row.get("implementation_role", "")).strip() != "high_risk_prototype"
    ]
    # Keep order while removing duplicates.
    return list(dict.fromkeys(tickers))


def main() -> None:
    args = _parse_args()
    end = args.end_date or datetime.now(timezone.utc).date().isoformat()
    if args.start_date:
        start = args.start_date
    else:
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        lookback_days = (
            int(args.years * 365.25) if args.years else DEFAULT_LOOKBACK_DAYS
        )
        start = (end_dt - timedelta(days=lookback_days)).isoformat()

    tickers = _resolve_tickers(args.universe)
    df = fetch_openbb_price_history(
        tickers,
        start_date=start,
        end_date=end,
        provider=args.provider,
    )

    output_path = Path(args.output)
    if args.output == str(DEFAULT_OUTPUT) and "data/samples" in output_path.as_posix():
        raise ValueError("Default output must be data/raw/openbb_price_history.csv")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    present = set(df["ticker"].astype(str).unique()) if not df.empty else set()
    missing = [t for t in tickers if t not in present]
    date_min = str(df["date"].min().date()) if not df.empty else "n/a"
    date_max = str(df["date"].max().date()) if not df.empty else "n/a"

    print(f"provider: {args.provider}")
    print(f"universe: {args.universe}")
    print(f"requested_tickers: {tickers}")
    print(f"ticker_count: {len(tickers)}")
    print(f"row_count: {len(df)}")
    print(f"date_range: {start} to {end} (observed {date_min} .. {date_max})")
    print(f"missing_tickers: {missing if missing else '(none)'}")
    if "VIX" in tickers and args.provider == DEFAULT_PROVIDER:
        print(f"vix_mapping_note: {VIX_MAPPING_NOTE}")
    print(f"output_path: {output_path.resolve()}")
    print(f"timestamp_utc: {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}")
    print(f"columns: {PRICE_HISTORY_COLUMNS}")


if __name__ == "__main__":
    main()
