"""Check whether the v2 web dashboard is ready for static/hosted deployment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "web_dashboard" / "snapshots"
WEB = ROOT / "web_dashboard"

REQUIRED_WEB_FILES = [
    "index.html",
    "market.html",
    "risk.html",
    "strategies.html",
    "shared.js",
    "styles.css",
]

REQUIRED_SNAPSHOTS = [
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
    "strategy_library.csv",
]

MOJIBAKE_MARKERS = ["鈥", "鈫", "鈮", "鈹", "�"]


def _json_ok(path: Path) -> bool:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)
    return True


def _scan_mojibake(paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    for name in REQUIRED_WEB_FILES:
        path = WEB / name
        if not path.exists():
            errors.append(f"missing web file: {path.relative_to(ROOT)}")

    for name in REQUIRED_SNAPSHOTS:
        path = SNAPSHOTS / name
        if not path.exists():
            errors.append(f"missing snapshot: {path.relative_to(ROOT)}")
            continue
        if path.suffix == ".json":
            try:
                _json_ok(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"invalid JSON {path.relative_to(ROOT)}: {exc}")

    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8", errors="replace")
        for pattern in ["data/raw/", "data/processed/", "output/", ".env"]:
            if pattern not in text:
                warnings.append(f".gitignore does not mention {pattern}")
    else:
        warnings.append(".gitignore missing")

    scan_paths = [WEB / name for name in REQUIRED_WEB_FILES if (WEB / name).exists()]
    scan_paths.extend(
        path for path in [ROOT / "README.md", ROOT / "DEPLOY_NOW.md", ROOT / "RUN_WORKSTATION.md"]
        if path.exists()
    )
    mojibake_hits = _scan_mojibake(scan_paths)
    if mojibake_hits:
        errors.append("mojibake markers found: " + ", ".join(mojibake_hits))

    print("Deployment readiness check")
    print(f"web files: {len(REQUIRED_WEB_FILES)} required")
    print(f"snapshots: {len(REQUIRED_SNAPSHOTS)} required")
    if warnings:
        print("warnings:")
        for item in warnings:
            print(f"- {item}")
    if errors:
        print("errors:")
        for item in errors:
            print(f"- {item}")
        return 1
    print("status: ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
