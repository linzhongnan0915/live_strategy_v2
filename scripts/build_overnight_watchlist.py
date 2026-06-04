"""Build overnight watchlist JSON from market monitor snapshot."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.monitoring.overnight_watchlist import (
    DEFAULT_MONITOR_SNAPSHOT_PATH,
    build_overnight_watchlist,
)

DEFAULT_OUTPUT_PATH = _ROOT / "output" / "openbb_overnight_watchlist.json"


def main(
    monitor_path: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    watchlist = build_overnight_watchlist(monitor_path or DEFAULT_MONITOR_SNAPSHOT_PATH)
    out_path = output_path or DEFAULT_OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(watchlist, handle, indent=2)

    summary = watchlist["summary"]
    urgent_count = sum(
        1 for item in watchlist["items"] if item.get("watch_level") == "urgent_review"
    )

    print(f"output: {out_path}")
    print(f"official_eod_date: {watchlist.get('official_eod_date')}")
    print(f"watchlist_count: {summary['watchlist_count']}")
    print(f"newer_than_official_eod_count: {summary['newer_than_official_eod_count']}")
    print(f"stale_count: {summary['stale_count']}")
    print(f"large_move_count: {summary['large_move_count']}")
    print(f"urgent_review_count: {urgent_count}")
    print("official_risk_decision_allowed: false")
    return watchlist


if __name__ == "__main__":
    main()
