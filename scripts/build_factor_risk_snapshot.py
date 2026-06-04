"""Build Barra-style / BlackRock-style ETF proxy factor risk snapshot.

This writes a dashboard artifact only. It does not claim to implement Barra.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.factors.factor_model import build_barra_style_factor_risk_snapshot

DEFAULT_PRICE_PATH = ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
DEFAULT_SIMULATION_PATH = ROOT / "output" / "portfolio_strategy_simulation_snapshot.json"
DEFAULT_OUTPUT_PATH = ROOT / "output" / "factor_risk_snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build factor risk dashboard snapshot.")
    parser.add_argument("--price-path", default=str(DEFAULT_PRICE_PATH))
    parser.add_argument("--simulation-path", default=str(DEFAULT_SIMULATION_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--expected-source", default="openbb_yfinance")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = build_barra_style_factor_risk_snapshot(
        price_path=args.price_path,
        simulation_path=args.simulation_path,
        as_of_date=args.as_of_date,
        expected_source=args.expected_source,
    )
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2, allow_nan=False)
    risk_rows = snapshot["factor_risk_contribution"]
    top_factor = risk_rows[0]["factor_name"] if risk_rows else "N/A"
    print(
        f"factor risk snapshot written path={output_path} "
        f"loadings={len(snapshot['factor_loading_matrix'])} "
        f"factors={len(risk_rows)} top_factor={top_factor}"
    )


if __name__ == "__main__":
    main()
