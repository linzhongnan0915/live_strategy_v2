"""Build prototype ETF strategy ranking snapshot for dashboard demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.strategy.strategy_ranker import build_ranking_snapshot

DEFAULT_OUTPUT_PATH = _ROOT / "output" / "strategy_ranking_snapshot.json"


def main(output_path: Path | None = None) -> dict:
    snapshot = build_ranking_snapshot()
    out_path = output_path or DEFAULT_OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)

    items = snapshot.get("items", [])
    print(f"output: {out_path}")
    print(f"strategy_count: {snapshot.get('strategy_count')}")
    print(f"data_coverage_warning_count: {snapshot.get('data_coverage_warning_count')}")
    print(f"sufficient_price_coverage_count: {snapshot.get('sufficient_price_coverage_count')}")
    print(f"partial_price_coverage_count: {snapshot.get('partial_price_coverage_count')}")
    print(f"insufficient_price_coverage_count: {snapshot.get('insufficient_price_coverage_count')}")
    print("prototype_not_backtest: true")
    print("\nTop 10 strategies:")
    for row in items[:10]:
        print(
            f"  {row['rank']}. {row['strategy_id']} | score={row['overall_score']} | "
            f"{row['review_status']} | {row['primary_factor']}"
        )
    return snapshot


if __name__ == "__main__":
    main()
