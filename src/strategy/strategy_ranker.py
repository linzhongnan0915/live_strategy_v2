"""
Prototype ETF strategy ranking engine (not a backtest or WFO result).

Scores strategies from price proxies, liquidity tiers, and rule-engine context.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.config_loader import (
    PROJECT_ROOT,
    load_etf_universe,
    load_strategy_library,
    load_strategy_scoring_policy,
)
from src.portfolio.metrics_builder import DEFAULT_PRICE_PATH

LIQUIDITY_SCORE_MAP = {
    "high": 0.90,
    "medium": 0.70,
    "low": 0.50,
    "monitor_only": 0.35,
}

DEFAULT_METRICS_PATH = PROJECT_ROOT / "output" / "openbb_metrics_snapshot.json"
DEFAULT_PROCESSED_PATH = (
    PROJECT_ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
)


def _load_price_panel() -> tuple[pd.DataFrame, str]:
    """Prefer broader OpenBB raw research panel; fall back to processed/sample."""
    raw_path = PROJECT_ROOT / "data" / "raw" / "openbb_price_history.csv"
    candidates = []
    if raw_path.exists():
        candidates.append((raw_path, "openbb_raw_research"))
    if DEFAULT_PROCESSED_PATH.exists():
        candidates.append((DEFAULT_PROCESSED_PATH, "openbb_processed"))
    candidates.append((DEFAULT_PRICE_PATH, "sample_synthetic"))

    best_df: pd.DataFrame | None = None
    best_label = ""
    best_count = -1
    for path, label in candidates:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"])
        count = int(df["ticker"].nunique())
        if count > best_count:
            best_df = df
            best_label = label
            best_count = count
    if best_df is None:
        raise FileNotFoundError("No strategy ranking price panel found")
    return best_df, best_label


def _pivot_research_close_prices(df: pd.DataFrame) -> pd.DataFrame:
    wide = df.pivot_table(
        index="date",
        columns="ticker",
        values="close",
        aggfunc="last",
    ).sort_index()
    wide.columns = [str(col).upper() for col in wide.columns]
    return wide


def _parse_target_etfs(value: str) -> list[str]:
    return [t.strip() for t in str(value).split(";") if t.strip()]


def _investable_tickers(etf_universe: pd.DataFrame) -> set[str]:
    """Tickers allowed to contribute to performance/risk ranking proxies."""
    blocked_roles = {"monitor_only", "high_risk_prototype"}
    allowed = etf_universe[
        ~etf_universe["implementation_role"].astype(str).str.strip().isin(blocked_roles)
    ]
    return set(allowed["ticker"].astype(str).str.upper())


def _ticker_returns(close_df: pd.DataFrame, ticker: str, lookback: int) -> float | None:
    if ticker not in close_df.columns:
        return None
    series = close_df[ticker].dropna()
    if len(series) <= lookback:
        return None
    end = float(series.iloc[-1])
    start = float(series.iloc[-1 - lookback])
    if start == 0:
        return None
    return end / start - 1.0


def _load_regime_context(metrics_path: Path | None = None) -> dict[str, Any]:
    path = metrics_path or DEFAULT_METRICS_PATH
    if not path.exists():
        path = PROJECT_ROOT / "data" / "samples" / "computed_metrics_snapshot.json"
    if not path.exists():
        return {"alerted_strategies": set(), "has_context": False}
    try:
        from src.regime.rule_engine import run_rule_engine

        result = run_rule_engine(metrics_path=path)
        alerted: set[str] = set()
        for frame_key in ("alerts", "primary_alerts"):
            frame = result.get(frame_key)
            if frame is None or frame.empty:
                continue
            for _, row in frame.iterrows():
                for part in str(row.get("affected_strategies", "")).split(";"):
                    part = part.strip()
                    if part:
                        alerted.add(part)
        return {"alerted_strategies": alerted, "has_context": True}
    except Exception:
        return {"alerted_strategies": set(), "has_context": False}


def _performance_score(returns_5d: list[float], returns_20d: list[float]) -> tuple[float, str]:
    parts: list[str] = []
    vals: list[float] = []
    if returns_5d:
        vals.append(float(np.mean(returns_5d)))
        parts.append(f"5d avg {np.mean(returns_5d):.2%}")
    if returns_20d:
        vals.append(float(np.mean(returns_20d)))
        parts.append(f"20d avg {np.mean(returns_20d):.2%}")
    if not vals:
        return 0.50, "neutral performance (no price coverage for target ETFs)"
    blended = float(np.mean(vals))
    score = float(np.clip(0.5 + blended / 0.10, 0.0, 1.0))
    return score, "performance proxy from " + "; ".join(parts)


def _risk_score(returns_20d: list[float]) -> tuple[float, str]:
    if not returns_20d:
        return 0.50, "neutral risk (no return history)"
    vol = float(np.std(returns_20d))
    worst = float(min(returns_20d))
    score = float(np.clip(1.0 - vol / 0.05 - abs(min(worst, 0)) / 0.10, 0.0, 1.0))
    return score, f"risk proxy vol={vol:.2%} worst_20d={worst:.2%}"


def _liquidity_score(
    tickers: list[str],
    etf_universe: pd.DataFrame,
) -> tuple[float, str]:
    tiers = etf_universe.set_index("ticker")["liquidity_tier"].astype(str).to_dict()
    scores = [LIQUIDITY_SCORE_MAP.get(tiers.get(t, "medium"), 0.60) for t in tickers]
    if not scores:
        return 0.50, "neutral liquidity (no ETF map match)"
    avg = float(np.mean(scores))
    return avg, f"liquidity tier average {avg:.2f}"


def _implementation_score(tickers: list[str], etf_universe: pd.DataFrame) -> tuple[float, str]:
    n = len(tickers)
    complexity_penalty = min(0.25, max(0, n - 4) * 0.03)
    liq, _ = _liquidity_score(tickers, etf_universe)
    score = float(np.clip(liq - complexity_penalty, 0.0, 1.0))
    return score, f"implementation score after {n} ETF complexity adjustment"


def _regime_fit_score(
    strategy_id: str,
    regime_ctx: dict[str, Any],
) -> tuple[float, str]:
    if not regime_ctx.get("has_context"):
        return 0.50, "neutral regime fit (no rule-engine context loaded)"
    if strategy_id in regime_ctx.get("alerted_strategies", set()):
        return 0.75, "elevated regime relevance (linked to active rule alerts)"
    return 0.55, "baseline regime fit (no active alert linkage)"


def _review_status(overall: float, risk_score: float, regime_fit: float) -> str:
    if regime_fit >= 0.74 and risk_score < 0.40:
        return "urgent_review"
    if overall >= 0.65:
        return "candidate_review"
    if overall < 0.35:
        return "avoid_for_now"
    return "monitor"


def _coverage_status(coverage_ratio: float) -> str:
    if coverage_ratio >= 0.80:
        return "sufficient"
    if coverage_ratio >= 0.50:
        return "partial"
    return "insufficient"


def _review_status_with_coverage(
    overall: float,
    risk_score: float,
    regime_fit: float,
    coverage_ratio: float,
) -> str:
    if coverage_ratio < 0.50:
        return "needs_price_data"
    if coverage_ratio < 0.80:
        return "research_only"
    return _review_status(overall, risk_score, regime_fit)


def _risk_level(risk_score: float) -> str:
    if risk_score >= 0.70:
        return "low"
    if risk_score >= 0.45:
        return "medium"
    return "high"


def rank_strategies(
    metrics_path: Path | str | None = None,
    config_dir: Path | str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Rank ETF strategies using prototype scoring policy."""
    _ = config_dir
    strategies = load_strategy_library()
    scoring = load_strategy_scoring_policy()
    etf_universe = load_etf_universe()
    investable = _investable_tickers(etf_universe)
    weights = scoring.set_index("score_component")["weight"].astype(float).to_dict()

    prices, price_source = _load_price_panel()
    close_df = _pivot_research_close_prices(prices)
    regime_ctx = _load_regime_context(
        Path(metrics_path) if metrics_path else None
    )

    rows: list[dict[str, Any]] = []
    coverage_warnings = 0

    for _, strat in strategies.iterrows():
        strategy_id = str(strat["strategy_id"])
        tickers = _parse_target_etfs(strat["target_etfs"])
        available = [t for t in tickers if t in investable and t in close_df.columns]
        missing = [t for t in tickers if t not in available]
        coverage_ratio = len(available) / len(tickers) if tickers else 0.0

        ret5 = [
            r for t in available if (r := _ticker_returns(close_df, t, 5)) is not None
        ]
        ret20 = [
            r for t in available if (r := _ticker_returns(close_df, t, 20)) is not None
        ]
        if missing:
            coverage_warnings += 1

        perf, perf_note = _performance_score(ret5, ret20)
        risk, risk_note = _risk_score(ret20)
        liq, liq_note = _liquidity_score(tickers, etf_universe)
        impl, impl_note = _implementation_score(tickers, etf_universe)
        regime, regime_note = _regime_fit_score(strategy_id, regime_ctx)

        overall = (
            perf * weights.get("performance_score", 0.30)
            + risk * weights.get("risk_score", 0.25)
            + regime * weights.get("regime_fit_score", 0.25)
            + liq * weights.get("liquidity_score", 0.10)
            + impl * weights.get("implementation_score", 0.10)
        )

        explanation_parts = [perf_note, risk_note, regime_note, liq_note, impl_note]
        if missing:
            explanation_parts.append(
                f"missing price coverage: {', '.join(missing)}"
            )

        rows.append(
            {
                "strategy_id": strategy_id,
                "category": str(strat["category"]),
                "objective": str(strat["objective"]),
                "target_etfs": ";".join(tickers),
                "primary_factor": str(strat["primary_factor"]),
                "secondary_factor": str(strat["secondary_factor"]),
                "available_price_etfs": ";".join(available),
                "missing_price_etfs": ";".join(missing),
                "price_coverage_ratio": round(coverage_ratio, 4),
                "price_coverage_status": _coverage_status(coverage_ratio),
                "performance_score": round(perf, 4),
                "risk_score": round(risk, 4),
                "regime_fit_score": round(regime, 4),
                "liquidity_score": round(liq, 4),
                "implementation_score": round(impl, 4),
                "overall_score": round(overall, 4),
                "risk_level": _risk_level(risk),
                "review_status": _review_status_with_coverage(
                    overall, risk, regime, coverage_ratio
                ),
                "explanation": " | ".join(explanation_parts),
            }
        )

    ranked = pd.DataFrame(rows).sort_values(
        "overall_score", ascending=False
    ).reset_index(drop=True)
    ranked.insert(0, "rank", ranked.index + 1)

    meta = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "data_mode": "strategy_ranking_prototype",
        "prototype_not_backtest": True,
        "price_source": price_source,
        "strategy_count": len(ranked),
        "data_coverage_warning_count": coverage_warnings,
        "sufficient_price_coverage_count": int(
            (ranked["price_coverage_status"] == "sufficient").sum()
        ),
        "partial_price_coverage_count": int(
            (ranked["price_coverage_status"] == "partial").sum()
        ),
        "insufficient_price_coverage_count": int(
            (ranked["price_coverage_status"] == "insufficient").sum()
        ),
        "official_risk_decision_allowed": False,
        "note": (
            "Prototype ranking for demo comparison only. Not walk-forward validated. "
            "Human review required before any strategy activation."
        ),
        "items": ranked.to_dict(orient="records"),
    }
    return ranked, meta


def build_ranking_snapshot(
    metrics_path: Path | str | None = None,
) -> dict[str, Any]:
    """JSON-serializable strategy ranking snapshot."""
    _, meta = rank_strategies(metrics_path=metrics_path)
    return meta


def snapshot_to_jsonable(snapshot: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(snapshot))
