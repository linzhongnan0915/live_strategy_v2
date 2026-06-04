"""Copy latest dashboard artifacts into web_dashboard/snapshots for static hosting.

The live workstation normally reads gitignored files from output/. Public static
hosting cannot see those files unless we publish a safe snapshot copy.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
SNAPSHOTS = ROOT / "web_dashboard" / "snapshots"
CONFIG = ROOT / "data" / "config"

JSON_ARTIFACTS = [
    "live_polling_status.json",
    "openbb_market_monitor_snapshot.json",
    "openbb_overnight_watchlist.json",
    "news_risk_snapshot.json",
    "macro_context_snapshot.json",
    "openbb_metrics_snapshot.json",
    "strategy_ranking_snapshot.json",
    "strategy_backtest_snapshot.json",
    "strategy_walk_forward_snapshot.json",
    "daily_strategy_review_snapshot.json",
    "portfolio_strategy_simulation_snapshot.json",
    "factor_risk_snapshot.json",
]

CSV_ARTIFACTS = [
    "strategy_library.csv",
]


def _copy_json(name: str) -> bool:
    src = OUTPUT / name
    if not src.exists():
        return False
    with src.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    dest = SNAPSHOTS / name
    with dest.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
    return True


def _copy_csv(name: str) -> bool:
    src = CONFIG / name
    if not src.exists():
        return False
    shutil.copyfile(src, SNAPSHOTS / name)
    return True


def main() -> None:
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    preserved: list[str] = []
    missing: list[str] = []

    for name in JSON_ARTIFACTS:
        if _copy_json(name):
            copied.append(name)
        elif (SNAPSHOTS / name).exists():
            preserved.append(name)
        else:
            missing.append(name)

    for name in CSV_ARTIFACTS:
        if _copy_csv(name):
            copied.append(name)
        else:
            missing.append(name)

    manifest = {
        "copied_count": len(copied),
        "preserved_count": len(preserved),
        "missing_count": len(missing),
        "copied": copied,
        "preserved": preserved,
        "missing": missing,
        "note": "Static fallback only. Live hosted deployments should prefer output/ artifacts.",
    }
    with (SNAPSHOTS / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    print(
        f"web snapshots prepared path={SNAPSHOTS} copied={len(copied)} preserved={len(preserved)} missing={len(missing)}"
    )
    if missing:
        print("missing:", ", ".join(missing))


if __name__ == "__main__":
    main()
