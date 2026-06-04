"""Build baseline ETF sleeve backtest snapshot for dashboard demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.backtesting.strategy_backtester import build_backtest_snapshot

DEFAULT_OUTPUT_PATH = _ROOT / "output" / "strategy_backtest_snapshot.json"


def main(output_path: Path | None = None) -> dict:
    snapshot = build_backtest_snapshot()
    out_path = output_path or DEFAULT_OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)

    print(f"output: {out_path}")
    print(f"strategy_count: {snapshot.get('strategy_count')}")
    print(f"price_source: {snapshot.get('price_source')}")
    print(f"sufficient_coverage_count: {snapshot.get('sufficient_coverage_count')}")
    print(f"partial_coverage_count: {snapshot.get('partial_coverage_count')}")
    print(f"insufficient_coverage_count: {snapshot.get('insufficient_coverage_count')}")
    print("prototype_baseline_backtest: true")
    print("\nTop 10 baseline sleeve backtests:")
    for row in snapshot.get("items", [])[:10]:
        print(
            f"  {row['final_backtest_rank']}. {row['strategy_id']} | "
            f"score={row['final_backtest_score']} | "
            f"total_return={row['total_return']} | "
            f"win_monthly={row['win_rate_monthly']} | "
            f"{row['backtest_status']}"
        )
    return snapshot


if __name__ == "__main__":
    main()
