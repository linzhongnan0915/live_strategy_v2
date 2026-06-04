"""Live-style OpenBB polling loop for the three-window workstation.

This is a prototype polling bridge, not Bloomberg streaming. It refreshes
market-monitor artifacts so the web dashboard screens can fetch the latest
shared state without full-page reloads.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.data.config_loader import load_etf_universe
from src.external.openbb_client import fetch_openbb_price_history
from src.external.friend_api_client import (
    DEFAULT_FRIEND_API_BASE,
    fetch_dxy_snapshot,
    fetch_econ_upcoming_snapshot,
)
from src.monitoring.live_market_snapshot import (
    build_market_monitor_snapshot,
    snapshot_to_jsonable,
)
from src.monitoring.overnight_watchlist import build_overnight_watchlist
from src.news.news_monitor import build_news_risk_snapshot

DEFAULT_PROVIDER = "yfinance"
DEFAULT_INTERVAL_SECONDS = 30
DEFAULT_LOOKBACK_DAYS = 10
DEFAULT_LIVE_RAW_PATH = _ROOT / "data" / "raw" / "openbb_live_price_history.csv"
DEFAULT_PROCESSED_PATH = _ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
DEFAULT_EOD_ANCHOR_PATH = _ROOT / "data" / "samples" / "openbb_eod_anchor.csv"
DEFAULT_MONITOR_PATH = _ROOT / "output" / "openbb_market_monitor_snapshot.json"
DEFAULT_WATCHLIST_PATH = _ROOT / "output" / "openbb_overnight_watchlist.json"
DEFAULT_STATUS_PATH = _ROOT / "output" / "live_polling_status.json"
DEFAULT_NEWS_RISK_PATH = _ROOT / "output" / "news_risk_snapshot.json"
DEFAULT_MACRO_CONTEXT_PATH = _ROOT / "output" / "macro_context_snapshot.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live-style OpenBB polling loop.")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--once", action="store_true", help="Run one polling cycle and exit")
    parser.add_argument("--live-raw-path", default=str(DEFAULT_LIVE_RAW_PATH))
    parser.add_argument("--processed-path", default=str(DEFAULT_PROCESSED_PATH))
    parser.add_argument("--monitor-path", default=str(DEFAULT_MONITOR_PATH))
    parser.add_argument("--watchlist-path", default=str(DEFAULT_WATCHLIST_PATH))
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--news-risk-path", default=str(DEFAULT_NEWS_RISK_PATH))
    parser.add_argument("--news-api-url", default=None)
    parser.add_argument("--friend-api-base-url", default=DEFAULT_FRIEND_API_BASE)
    parser.add_argument("--macro-context-path", default=str(DEFAULT_MACRO_CONTEXT_PATH))
    parser.add_argument(
        "--market-data-mode",
        choices=["openbb", "none"],
        default="openbb",
        help="Use none for news-only 1s polling when market data is updated elsewhere.",
    )
    return parser.parse_args()


def _resolve_live_tickers() -> list[str]:
    universe = load_etf_universe()
    tickers = [
        str(row["ticker"]).strip().upper()
        for _, row in universe.iterrows()
        if str(row.get("implementation_role", "")).strip() != "high_risk_prototype"
    ]
    return list(dict.fromkeys(tickers))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _resolve_processed_anchor(processed_path: Path) -> Path:
    """Use full processed EOD panel locally, or committed EOD anchor on hosted deploys."""
    if processed_path.exists():
        return processed_path
    if DEFAULT_EOD_ANCHOR_PATH.exists():
        return DEFAULT_EOD_ANCHOR_PATH
    return processed_path


def _status_payload(
    *,
    status: str,
    cycle: int,
    message: str,
    provider: str,
    market_data_mode: str,
    interval_seconds: int,
    ticker_count: int,
    row_count: int = 0,
    latest_observed_date: str | None = None,
    news_status: str | None = None,
    news_max_severity: float | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    next_poll = now + timedelta(seconds=interval_seconds)
    market_data_active = market_data_mode == "openbb"
    data_mode = (
        "live_polling_openbb_yfinance_prototype"
        if market_data_active
        else "news_only_friend_api_monitor"
    )
    return {
        "generated_at_utc": now.isoformat(),
        "status": status,
        "cycle": cycle,
        "message": message,
        "provider": provider if market_data_active else "none",
        "market_data_mode": market_data_mode,
        "market_data_active": market_data_active,
        "interval_seconds": interval_seconds,
        "next_poll_after_utc": next_poll.isoformat(),
        "ticker_count": ticker_count if market_data_active else 0,
        "configured_market_ticker_count": ticker_count,
        "row_count": row_count,
        "latest_observed_date": latest_observed_date,
        "news_status": news_status,
        "news_max_severity": news_max_severity,
        "error": error,
        "data_mode": data_mode,
        "official_risk_decision_allowed": False,
        "note": (
            "News-only polling updates news/macro artifacts only."
            if not market_data_active
            else (
                "Live-style polling updates market monitor/watchlist artifacts only. "
                "Official EOD risk decisions still require processed EOD quality gates."
            )
        ),
    }


def run_poll_cycle(
    *,
    cycle: int,
    provider: str,
    interval_seconds: int,
    lookback_days: int,
    live_raw_path: Path,
    processed_path: Path,
    monitor_path: Path,
    watchlist_path: Path,
    status_path: Path,
    news_risk_path: Path,
    macro_context_path: Path,
    news_api_url: str | None = None,
    friend_api_base_url: str = DEFAULT_FRIEND_API_BASE,
    market_data_mode: str = "openbb",
) -> dict[str, Any]:
    tickers = _resolve_live_tickers()
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback_days)

    try:
        row_count = 0
        latest = None
        monitor_payload: dict[str, Any] | None = None
        if market_data_mode == "openbb":
            df = fetch_openbb_price_history(
                tickers,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                provider=provider,
            )
            if df.empty:
                raise ValueError("OpenBB live poll returned no rows")

            live_raw_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(live_raw_path, index=False)

            monitor = build_market_monitor_snapshot(
                raw_price_path=live_raw_path,
                processed_price_path=_resolve_processed_anchor(processed_path),
                monitor_tickers=tickers,
            )
            monitor_payload = snapshot_to_jsonable(monitor)
            _write_json(monitor_path, monitor_payload)

            watchlist = build_overnight_watchlist(monitor_path)
            _write_json(watchlist_path, watchlist)

            latest = pd.to_datetime(df["date"], errors="coerce").max().date().isoformat()
            row_count = len(df)

        news_snapshot = build_news_risk_snapshot(
            api_url=news_api_url,
            market_items=(monitor_payload or {}).get("items"),
        )
        _write_json(news_risk_path, news_snapshot)
        try:
            dxy_snapshot = fetch_dxy_snapshot(friend_api_base_url)
        except Exception as exc:
            dxy_snapshot = {
                "status": "failed",
                "error": str(exc),
                "official_risk_decision_allowed": False,
                "note": "DXY endpoint unavailable; continue market/news monitoring.",
            }
        try:
            upcoming_snapshot = fetch_econ_upcoming_snapshot(friend_api_base_url, days=14)
        except Exception as exc:
            upcoming_snapshot = {
                "status": "failed",
                "event_count": 0,
                "events": [],
                "error": str(exc),
                "official_risk_decision_allowed": False,
                "note": "Economic calendar endpoint unavailable; continue market/news monitoring.",
            }
        macro_context = {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "data_mode": "friend_api_macro_context",
            "official_risk_decision_allowed": False,
            "dxy": dxy_snapshot,
            "upcoming_events": upcoming_snapshot,
            "note": "Macro context supports risk review; not execution.",
        }
        _write_json(macro_context_path, macro_context)
        status = _status_payload(
            status="success",
            cycle=cycle,
            message="live poll updated shared market/news artifacts",
            provider=provider,
            market_data_mode=market_data_mode,
            interval_seconds=interval_seconds,
            ticker_count=len(tickers),
            row_count=row_count,
            latest_observed_date=latest,
            news_status=news_snapshot.get("status"),
            news_max_severity=float(news_snapshot.get("max_severity", 0.0)),
        )
        _write_json(status_path, status)
        return status
    except Exception as exc:
        status = _status_payload(
            status="failed",
            cycle=cycle,
            message="live poll failed; existing artifacts were not refreshed",
            provider=provider,
            market_data_mode=market_data_mode,
            interval_seconds=interval_seconds,
            ticker_count=len(tickers),
            error=str(exc),
        )
        _write_json(status_path, status)
        return status


def main() -> None:
    args = _parse_args()
    if args.interval_seconds < 1:
        raise ValueError("--interval-seconds must be >= 1")

    live_raw_path = Path(args.live_raw_path)
    processed_path = Path(args.processed_path)
    monitor_path = Path(args.monitor_path)
    watchlist_path = Path(args.watchlist_path)
    status_path = Path(args.status_path)
    news_risk_path = Path(args.news_risk_path)
    macro_context_path = Path(args.macro_context_path)

    cycle = 1
    if args.interval_seconds < 15 and args.market_data_mode == "openbb":
        print(
            "warning: OpenBB/yfinance polling below 15s may be rate-limited; "
            "prefer --market-data-mode none for 1s news/friend-API demos."
        )
    while True:
        status = run_poll_cycle(
            cycle=cycle,
            provider=args.provider,
            interval_seconds=args.interval_seconds,
            lookback_days=args.lookback_days,
            live_raw_path=live_raw_path,
            processed_path=processed_path,
            monitor_path=monitor_path,
            watchlist_path=watchlist_path,
            status_path=status_path,
            news_risk_path=news_risk_path,
            macro_context_path=macro_context_path,
            news_api_url=args.news_api_url,
            friend_api_base_url=args.friend_api_base_url,
            market_data_mode=args.market_data_mode,
        )
        print(
            f"cycle={cycle} status={status['status']} "
            f"latest={status.get('latest_observed_date')} rows={status.get('row_count')} "
            f"news={status.get('news_status')} severity={status.get('news_max_severity')} "
            f"message={status['message']}"
        )
        if args.once:
            break
        cycle += 1
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
