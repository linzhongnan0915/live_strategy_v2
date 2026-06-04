"""Client helpers for the situation-monitor friend API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

DEFAULT_FRIEND_API_BASE = "https://news.tcx086.com"


def _get_json(url: str, timeout_seconds: int = 10) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "live-strategy/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"friend API response must be object: {url}")
    return payload


def fetch_dxy_snapshot(
    base_url: str = DEFAULT_FRIEND_API_BASE,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Fetch DXY macro factor snapshot from friend API."""
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "markets/dxy")
    payload = _get_json(url, timeout_seconds=timeout_seconds)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "success" if payload.get("ok") is not False else "failed",
        "symbol": payload.get("symbol"),
        "name": payload.get("name"),
        "data_source": payload.get("dataSource"),
        "current": data.get("current"),
        "change": data.get("change"),
        "change_percent": data.get("changePercent"),
        "previous": data.get("previous"),
        "date": data.get("date"),
        "official_risk_decision_allowed": False,
        "note": "DXY is macro factor context only; not an execution signal.",
    }


def fetch_econ_upcoming_snapshot(
    base_url: str = DEFAULT_FRIEND_API_BASE,
    days: int = 14,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Fetch upcoming economic events from friend API."""
    query = urllib.parse.urlencode({"days": days})
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"econ/upcoming?{query}")
    payload = _get_json(url, timeout_seconds=timeout_seconds)
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "success" if payload.get("ok") is not False else "failed",
        "horizon_days": payload.get("horizon_days", days),
        "event_count": len(events),
        "events": events[:20],
        "official_risk_decision_allowed": False,
        "note": "Economic calendar is next-day/watchlist context only.",
    }
