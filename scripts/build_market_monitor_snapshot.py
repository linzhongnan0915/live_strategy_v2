"""Build read-only OpenBB market monitor snapshot JSON."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.monitoring.live_market_snapshot import (
    DEFAULT_PROCESSED_PATH,
    DEFAULT_RAW_PATH,
    build_market_monitor_snapshot,
    snapshot_to_jsonable,
)

DEFAULT_OUTPUT_PATH = _ROOT / "output" / "openbb_market_monitor_snapshot.json"


def main(
    raw_path: Path | None = None,
    processed_path: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    snapshot = build_market_monitor_snapshot(
        raw_price_path=raw_path or DEFAULT_RAW_PATH,
        processed_price_path=processed_path or DEFAULT_PROCESSED_PATH,
    )
    payload = snapshot_to_jsonable(snapshot)
    out_path = output_path or DEFAULT_OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    timing_counts = Counter(item["timing_status"] for item in payload["items"])
    stale_count = sum(1 for item in payload["items"] if item["is_stale"])

    print(f"output: {out_path}")
    print(f"generated_at_utc: {payload['generated_at_utc']}")
    print(f"official_eod_date: {payload['official_eod_date']}")
    print(f"ticker_count: {payload['ticker_count']}")
    print(f"official_eod_aligned: {timing_counts.get('official_eod_aligned', 0)}")
    print(f"newer_than_official_eod: {timing_counts.get('newer_than_official_eod', 0)}")
    print(f"stale_vs_official_eod: {timing_counts.get('stale_vs_official_eod', 0)}")
    print(f"is_stale_count: {stale_count}")
    print("official_risk_decision_allowed: false")
    return payload


if __name__ == "__main__":
    main()
