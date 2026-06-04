"""Build walk-forward strategy evaluation snapshot for dashboard demo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.backtesting.strategy_backtester import build_walk_forward_snapshot

DEFAULT_OUTPUT_PATH = _ROOT / "output" / "strategy_walk_forward_snapshot.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run WFO-style rolling out-of-sample evaluation for ETF strategies."
    )
    parser.add_argument("--price-path", default=None, help="Optional long-format price CSV")
    parser.add_argument("--train-years", type=int, default=5)
    parser.add_argument("--test-months", type=int, default=12)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main(
    output_path: Path | None = None,
    price_path: Path | str | None = None,
    train_years: int = 5,
    test_months: int = 12,
    step_months: int = 3,
    top_n: int = 5,
) -> dict:
    snapshot = build_walk_forward_snapshot(
        price_path=price_path,
        train_years=train_years,
        test_months=test_months,
        step_months=step_months,
        top_n=top_n,
    )
    out_path = output_path or DEFAULT_OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2, allow_nan=False)

    print(f"output: {out_path}")
    print(f"price_source: {snapshot.get('price_source')}")
    print(f"price_start_date: {snapshot.get('price_start_date')}")
    print(f"price_end_date: {snapshot.get('price_end_date')}")
    print(f"approx_years: {snapshot.get('approx_years')}")
    print(f"strategy_count: {snapshot.get('strategy_count')}")
    print(f"window_count: {snapshot.get('window_count')}")
    print(f"train_years: {snapshot.get('train_years')}")
    print(f"test_months: {snapshot.get('test_months')}")
    print("walk_forward_optimization: true")
    print("official_risk_decision_allowed: false")
    if not snapshot.get("items"):
        print(f"note: {snapshot.get('note')}")
        return snapshot

    print("\nTop 10 WFO strategy evaluations:")
    for row in snapshot.get("items", [])[:10]:
        print(
            f"  {row['wfo_rank']}. {row['strategy_id']} | "
            f"score={row['wfo_score']} | "
            f"windows={row['window_count']} | "
            f"top5_hit={row['train_top5_hit_rate']} | "
            f"oos_avg_return={row['oos_avg_total_return']} | "
            f"oos_positive={row['oos_positive_window_rate']} | "
            f"{row['wfo_status']}"
        )
    return snapshot


if __name__ == "__main__":
    args = _parse_args()
    main(
        output_path=Path(args.output),
        price_path=args.price_path,
        train_years=args.train_years,
        test_months=args.test_months,
        step_months=args.step_months,
        top_n=args.top_n,
    )
