"""
Overnight watchlist from market monitor snapshot (context only).

Flags newer-than-EOD, stale, and large-move observations for pre-open review.
Does not alter official EOD risk decisions, rule engine, or escalation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data.config_loader import PROJECT_ROOT

DATA_MODE = "overnight_watchlist_monitor_only"
WATCHLIST_NOTE = (
    "Overnight watchlist is context only and does not alter official EOD risk decisions. "
    "Review flagged items before next open; no automatic strategy switch."
)

DEFAULT_MONITOR_SNAPSHOT_PATH = (
    PROJECT_ROOT / "output" / "openbb_market_monitor_snapshot.json"
)
WATCH_LEVEL_RANK = {"urgent_review": 0, "watch": 1, "info": 2}


def _validate_monitor_snapshot(monitor: dict[str, Any]) -> None:
    if not isinstance(monitor, dict):
        raise ValueError("market monitor snapshot must be a JSON object")
    if not monitor.get("official_eod_date"):
        raise ValueError("market monitor snapshot missing official_eod_date")
    if not isinstance(monitor.get("items"), list):
        raise ValueError("market monitor snapshot items must be a list")
    if monitor.get("official_risk_decision_allowed") is True:
        raise ValueError(
            "overnight watchlist requires monitor-only input; "
            "official_risk_decision_allowed must not be true"
        )


def _coerce_return_pct(value: Any, ticker: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"latest_return_pct for {ticker or '(unknown ticker)'} must be numeric or null"
        ) from exc


def _resolve_watch_level(
    ticker: str,
    reasons: list[str],
    latest_return_pct: float | None,
    vix_large_move_threshold_pct: float,
) -> str:
    if (
        ticker == "VIX"
        and latest_return_pct is not None
        and abs(latest_return_pct) >= vix_large_move_threshold_pct
        and "large_move" in reasons
    ):
        return "urgent_review"
    return "watch"


def _evaluate_monitor_item(
    item: dict[str, Any],
    large_move_threshold_pct: float,
    vix_large_move_threshold_pct: float,
) -> dict[str, Any] | None:
    reasons: list[str] = []

    if item.get("timing_status") == "newer_than_official_eod":
        reasons.append("newer_than_official_eod")
    if item.get("is_stale"):
        reasons.append("stale_data")

    ticker = str(item.get("ticker", ""))
    latest_return_pct = _coerce_return_pct(item.get("latest_return_pct"), ticker)
    if latest_return_pct is not None:
        threshold = (
            vix_large_move_threshold_pct
            if ticker == "VIX"
            else large_move_threshold_pct
        )
        if abs(latest_return_pct) >= threshold:
            reasons.append("large_move")

    if not reasons:
        return None

    watch_level = _resolve_watch_level(
        ticker, reasons, latest_return_pct, vix_large_move_threshold_pct
    )

    return {
        "ticker": ticker,
        "asset_class": item.get("asset_class"),
        "risk_bucket": item.get("risk_bucket"),
        "target_weight": item.get("target_weight"),
        "latest_date": item.get("latest_date"),
        "official_eod_date": item.get("official_eod_date"),
        "latest_close": item.get("latest_close"),
        "latest_return_pct": latest_return_pct,
        "timing_status": item.get("timing_status"),
        "is_stale": item.get("is_stale"),
        "watch_reason": "; ".join(reasons),
        "watch_level": watch_level,
        "official_action_allowed": False,
    }


def _sort_watch_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda row: (
            WATCH_LEVEL_RANK.get(str(row.get("watch_level")), 99),
            -abs(float(row.get("latest_return_pct") or 0.0)),
            str(row.get("ticker", "")),
        ),
    )


def build_overnight_watchlist(
    monitor_snapshot_path: Path | str,
    large_move_threshold_pct: float = 2.0,
    vix_large_move_threshold_pct: float = 5.0,
) -> dict[str, Any]:
    """Build overnight watchlist rows from market monitor snapshot JSON."""
    path = Path(monitor_snapshot_path)
    if not path.exists():
        raise FileNotFoundError(
            f"market monitor snapshot not found: {path}. "
            "Run python scripts/build_market_monitor_snapshot.py first."
        )

    with path.open(encoding="utf-8") as handle:
        monitor = json.load(handle)
    _validate_monitor_snapshot(monitor)

    official_eod_date = monitor.get("official_eod_date")
    monitor_items = monitor.get("items", [])
    watch_items: list[dict[str, Any]] = []

    for item in monitor_items:
        row = _evaluate_monitor_item(
            item,
            large_move_threshold_pct=large_move_threshold_pct,
            vix_large_move_threshold_pct=vix_large_move_threshold_pct,
        )
        if row is not None:
            watch_items.append(row)
    watch_items = _sort_watch_items(watch_items)

    newer_count = sum(
        1 for row in watch_items if "newer_than_official_eod" in row["watch_reason"]
    )
    stale_count = sum(1 for row in watch_items if "stale_data" in row["watch_reason"])
    large_move_count = sum(1 for row in watch_items if "large_move" in row["watch_reason"])

    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "monitor_snapshot_path": str(path.resolve()),
        "official_eod_date": official_eod_date,
        "data_mode": DATA_MODE,
        "official_risk_decision_allowed": False,
        "note": WATCHLIST_NOTE,
        "summary": {
            "item_count": len(monitor_items),
            "newer_than_official_eod_count": newer_count,
            "stale_count": stale_count,
            "large_move_count": large_move_count,
            "watchlist_count": len(watch_items),
        },
        "items": watch_items,
    }
