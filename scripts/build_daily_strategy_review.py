"""Build after-market daily strategy review snapshot.

This produces a generated artifact for the Strategy screen. It combines
walk-forward evaluation, baseline backtest evidence, strategy definitions,
market monitor context, and news impact. It is review support only, not a
trade recommendation.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WFO_PATH = ROOT / "output" / "strategy_walk_forward_snapshot.json"
DEFAULT_BACKTEST_PATH = ROOT / "output" / "strategy_backtest_snapshot.json"
DEFAULT_RANKING_PATH = ROOT / "output" / "strategy_ranking_snapshot.json"
DEFAULT_MARKET_PATH = ROOT / "output" / "openbb_market_monitor_snapshot.json"
DEFAULT_NEWS_PATH = ROOT / "output" / "news_risk_snapshot.json"
DEFAULT_STRATEGY_LIBRARY_PATH = ROOT / "data" / "config" / "strategy_library.csv"
DEFAULT_OUTPUT_PATH = ROOT / "output" / "daily_strategy_review_snapshot.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _load_strategy_library(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {str(row.get("strategy_id", "")): row for row in rows}


def _market_confirmation_count(market: dict[str, Any]) -> int:
    items = {row.get("ticker"): row for row in market.get("items", [])}

    def num(ticker: str, field: str) -> float | None:
        try:
            return float(items.get(ticker, {}).get(field))
        except (TypeError, ValueError):
            return None

    count = 0
    spy = num("SPY", "latest_return_pct")
    hyg = num("HYG", "latest_return_pct")
    lqd = num("LQD", "latest_return_pct")
    vix = num("VIX", "latest_close")
    gld = num("GLD", "latest_return_pct")
    uso = num("USO", "latest_return_pct")
    if spy is not None and spy <= -0.75:
        count += 1
    if hyg is not None and lqd is not None and (hyg - lqd) <= -0.3:
        count += 1
    if vix is not None and vix >= 20:
        count += 1
    if (gld is not None and gld >= 1) or (uso is not None and uso >= 1.5):
        count += 1
    return count


def _derive_news_impact(news: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    severity = float(news.get("max_severity", 0.0) or 0.0)
    affected = news.get("affected_strategies", []) or []
    review_count = sum(1 for item in news.get("items", []) if item.get("requires_human_review"))
    confirmations = _market_confirmation_count(market)

    level = "green"
    reason = "No material market-relevant news impact."
    if severity >= 8 and (affected or confirmations >= 2 or review_count > 0):
        level = "red"
        reason = "High-severity news has strategy linkage, human-review flag, or cross-market confirmation."
    elif severity >= 5 and (affected or confirmations >= 1 or review_count > 0):
        level = "yellow"
        reason = "News is relevant enough for monitoring, but not independently decisive."
    elif severity >= 8:
        level = "yellow"
        reason = "High raw severity, but no strategy linkage or market confirmation; cap at watch."
    elif severity >= 5:
        level = "yellow"
        reason = "Moderate raw severity; monitor only."
    return {
        "level": level,
        "severity": severity,
        "affected_strategy_count": len(affected),
        "human_review_news_count": review_count,
        "market_confirmation_count": confirmations,
        "reason": reason,
    }


def build_daily_strategy_review() -> dict[str, Any]:
    wfo = _load_json(DEFAULT_WFO_PATH)
    backtest = _load_json(DEFAULT_BACKTEST_PATH)
    ranking = _load_json(DEFAULT_RANKING_PATH)
    market = _load_json(DEFAULT_MARKET_PATH)
    news = _load_json(DEFAULT_NEWS_PATH)
    library = _load_strategy_library(DEFAULT_STRATEGY_LIBRARY_PATH)

    backtest_by_id = {row.get("strategy_id"): row for row in backtest.get("items", [])}
    ranking_by_id = {row.get("strategy_id"): row for row in ranking.get("items", [])}
    news_impact = _derive_news_impact(news, market)

    items: list[dict[str, Any]] = []
    for row in wfo.get("items", []):
        strategy_id = row.get("strategy_id")
        config = library.get(strategy_id, {})
        bt = backtest_by_id.get(strategy_id, {})
        rk = ranking_by_id.get(strategy_id, {})

        action = "Maintain watch"
        if (
            int(row.get("wfo_rank", 999) or 999) <= 5
            and float(row.get("oos_positive_window_rate", 0.0) or 0.0) >= 0.6
            and news_impact["level"] != "red"
        ):
            action = "Candidate for review"
        if float(row.get("oos_avg_max_drawdown", 0.0) or 0.0) <= -0.18 or news_impact["level"] == "red":
            action = "Risk review before any use"

        items.append(
            {
                "strategy_id": strategy_id,
                "action": action,
                "wfo_rank": row.get("wfo_rank"),
                "wfo_score": row.get("wfo_score"),
                "wfo_status": row.get("wfo_status"),
                "category": row.get("category") or config.get("category", ""),
                "window_count": row.get("window_count"),
                "selected_top5_window_count": row.get("selected_top5_window_count"),
                "train_top5_hit_rate": row.get("train_top5_hit_rate"),
                "oos_avg_total_return": row.get("oos_avg_total_return"),
                "oos_avg_sharpe": row.get("oos_avg_sharpe"),
                "oos_avg_max_drawdown": row.get("oos_avg_max_drawdown"),
                "oos_avg_monthly_win_rate": row.get("oos_avg_monthly_win_rate"),
                "oos_positive_window_rate": row.get("oos_positive_window_rate"),
                "selected_oos_avg_total_return": row.get("selected_oos_avg_total_return"),
                "selected_oos_positive_window_rate": row.get("selected_oos_positive_window_rate"),
                "first_test_start": row.get("first_test_start"),
                "last_test_end": row.get("last_test_end"),
                "annualized_return": bt.get("annualized_return"),
                "win_rate_monthly": bt.get("win_rate_monthly"),
                "max_drawdown": bt.get("max_drawdown"),
                "objective": config.get("objective") or rk.get("explanation", ""),
                "core_signal": config.get("core_signal", ""),
                "target_etfs": config.get("target_etfs") or rk.get("target_etfs", ""),
                "available_price_etfs": row.get("available_price_etfs") or bt.get("available_price_etfs", ""),
                "missing_price_etfs": row.get("missing_price_etfs") or bt.get("missing_price_etfs", ""),
                "price_coverage_ratio": row.get("price_coverage_ratio") or bt.get("price_coverage_ratio"),
                "price_coverage_status": row.get("price_coverage_status") or bt.get("price_coverage_status"),
                "risk_controls": config.get("risk_controls", ""),
                "valid_regime": config.get("valid_regime", ""),
                "invalid_regime": config.get("invalid_regime", ""),
                "evidence_note": row.get("explanation", ""),
            }
        )

    as_of_date = market.get("official_eod_date") or market.get("latest_observed_date")
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "as_of_date": as_of_date,
        "data_mode": "after_market_daily_strategy_review",
        "official_risk_decision_allowed": False,
        "strategy_count": len(items),
        "ranking_basis": (
            "Walk-forward score first: OOS return, OOS Sharpe, OOS drawdown, "
            "positive OOS windows, and train-window top-5 stability. "
            "10-year baseline backtest is secondary evidence."
        ),
        "backtest_span": f"{backtest.get('price_start_date', 'N/A')} to {backtest.get('price_end_date', 'N/A')}",
        "wfo_setup": {
            "train_years": wfo.get("train_years"),
            "test_months": wfo.get("test_months"),
            "step_months": wfo.get("step_months"),
            "window_count": wfo.get("window_count"),
        },
        "wfo_windows": wfo.get("windows", []),
        "news_impact": news_impact,
        "items": items,
        "note": "Generated review support only. Human review is required before strategy use.",
    }


def main() -> None:
    payload = build_daily_strategy_review()
    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
    print(
        "daily strategy review written "
        f"path={DEFAULT_OUTPUT_PATH} strategies={payload['strategy_count']} "
        f"as_of={payload.get('as_of_date')}"
    )


if __name__ == "__main__":
    main()
