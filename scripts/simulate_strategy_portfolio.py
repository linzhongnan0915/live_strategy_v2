"""Simulate strategy-guided ETF portfolio from a fixed start date.

The simulation is designed for dashboard evidence, not trade execution.
Selection is rolling and no-look-ahead: each monthly rebalance uses only price
history available before that rebalance date.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtesting.strategy_backtester import (  # noqa: E402
    _max_drawdown,
    _monthly_returns,
    _pivot_close_prices,
    _read_price_csv,
    _total_return,
    parse_target_etfs,
)
from src.data.config_loader import load_strategy_library  # noqa: E402

DEFAULT_PRICE_PATH = ROOT / "data" / "raw" / "openbb_price_history.csv"
DEFAULT_OUTPUT_PATH = ROOT / "output" / "portfolio_strategy_simulation_snapshot.json"
INITIAL_CAPITAL = 1_000_000.0
SIMULATION_START = "2025-01-01"
TRAIN_YEARS = 5


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (pd.isna(value) or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value


def _strategy_returns(close: pd.DataFrame, target_etfs: list[str]) -> pd.Series:
    available = [ticker for ticker in target_etfs if ticker in close.columns]
    if not available:
        return pd.Series(dtype=float)
    returns = close[available].pct_change(fill_method=None)
    out = returns.mean(axis=1, skipna=True).dropna()
    out.name = "strategy_return"
    return out


def _metrics(returns: pd.Series) -> dict[str, float | None]:
    returns = returns.dropna()
    if returns.empty:
        return {
            "total_return": None,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_proxy": None,
            "max_drawdown": None,
            "monthly_win_rate": None,
            "observation_count": 0,
        }
    total = _total_return(returns)
    obs = len(returns)
    ann_return = (1 + total) ** (252 / obs) - 1 if total is not None and total > -1 else None
    ann_vol = float(returns.std(ddof=0) * (252 ** 0.5))
    monthly = _monthly_returns(returns)
    return {
        "total_return": float(total) if total is not None else None,
        "annualized_return": float(ann_return) if ann_return is not None else None,
        "annualized_volatility": ann_vol,
        "sharpe_proxy": float(ann_return / ann_vol) if ann_return is not None and ann_vol > 0 else None,
        "max_drawdown": float(_max_drawdown(returns)),
        "monthly_win_rate": float((monthly > 0).mean()) if len(monthly) else None,
        "observation_count": int(obs),
    }


def _score_candidates(metrics_by_strategy: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(metrics_by_strategy)
    if frame.empty:
        return []

    def pct(col: str, higher: bool = True) -> pd.Series:
        numeric = pd.to_numeric(frame[col], errors="coerce")
        fill = numeric.min() if higher else numeric.max()
        filled = numeric.fillna(fill)
        if filled.nunique() <= 1:
            return pd.Series(0.5, index=frame.index)
        return filled.rank(pct=True, ascending=higher)

    frame["selection_score"] = (
        0.20 * pct("total_return")
        + 0.32 * pct("sharpe_proxy")
        + 0.28 * pct("max_drawdown")
        + 0.15 * pct("monthly_win_rate")
        + 0.05 * pct("annualized_volatility", higher=False)
    )
    frame["risk_gate_pass"] = (
        (pd.to_numeric(frame["max_drawdown"], errors="coerce") >= -0.22)
        & (pd.to_numeric(frame["annualized_volatility"], errors="coerce") <= 0.28)
    )
    frame = frame.sort_values(
        ["risk_gate_pass", "selection_score", "sharpe_proxy"],
        ascending=[False, False, False],
    )
    return frame.to_dict(orient="records")


def _first_trading_days(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    frame = pd.DataFrame({"date": dates})
    frame["month"] = frame["date"].dt.to_period("M")
    return frame.groupby("month")["date"].min().tolist()


def build_strategy_simulation(
    *,
    price_path: Path | str = DEFAULT_PRICE_PATH,
    initial_capital: float = INITIAL_CAPITAL,
    start_date: str = SIMULATION_START,
    train_years: int = TRAIN_YEARS,
) -> dict[str, Any]:
    prices = _read_price_csv(Path(price_path))
    close = _pivot_close_prices(prices)
    strategies = load_strategy_library()
    strategy_configs = {
        str(row["strategy_id"]): {
            "strategy_id": str(row["strategy_id"]),
            "strategy_name": str(row.get("strategy_name", row["strategy_id"])),
            "category": str(row.get("category", "")),
            "objective": str(row.get("objective", "")),
            "target_etfs": parse_target_etfs(row["target_etfs"]),
            "core_signal": str(row.get("core_signal", "")),
            "risk_controls": str(row.get("risk_controls", "")),
        }
        for _, row in strategies.iterrows()
    }
    returns_by_strategy = {
        sid: _strategy_returns(close, config["target_etfs"])
        for sid, config in strategy_configs.items()
    }

    sim_start = pd.Timestamp(start_date)
    available_dates = pd.DatetimeIndex(close.index[close.index >= sim_start])
    if available_dates.empty:
        raise ValueError(f"No price dates available on or after {start_date}")
    rebalance_dates = _first_trading_days(available_dates)

    equity = initial_capital
    curve: list[dict[str, Any]] = []
    selection_log: list[dict[str, Any]] = []
    active_strategy: str | None = None
    active_rets = pd.Series(dtype=float)

    for i, rebalance_date in enumerate(rebalance_dates):
        train_end_candidates = close.index[close.index < rebalance_date]
        if train_end_candidates.empty:
            continue
        train_end = pd.Timestamp(train_end_candidates.max())
        train_start = train_end - pd.DateOffset(years=train_years)

        candidates: list[dict[str, Any]] = []
        for sid, rets in returns_by_strategy.items():
            train = rets[(rets.index >= train_start) & (rets.index <= train_end)].dropna()
            if len(train) < 504:
                continue
            candidates.append({"strategy_id": sid, **_metrics(train)})
        scored = _score_candidates(candidates)
        if not scored:
            continue

        selected = scored[0]
        active_strategy = str(selected["strategy_id"])
        active_rets = returns_by_strategy[active_strategy]
        test_end = rebalance_dates[i + 1] - pd.Timedelta(days=1) if i + 1 < len(rebalance_dates) else available_dates.max()
        hold = active_rets[(active_rets.index >= rebalance_date) & (active_rets.index <= test_end)].dropna()

        selection_log.append(
            {
                "rebalance_date": rebalance_date.date().isoformat(),
                "train_start": train_start.date().isoformat(),
                "train_end": train_end.date().isoformat(),
                "selected_strategy": active_strategy,
                "selected_strategy_name": strategy_configs[active_strategy]["strategy_name"],
                "selection_score": round(float(selected["selection_score"]), 4),
                "risk_gate_pass": bool(selected["risk_gate_pass"]),
                "train_total_return": selected["total_return"],
                "train_sharpe": selected["sharpe_proxy"],
                "train_max_drawdown": selected["max_drawdown"],
                "train_monthly_win_rate": selected["monthly_win_rate"],
                "top_candidates": [
                    {
                        "strategy_id": row["strategy_id"],
                        "score": round(float(row["selection_score"]), 4),
                        "sharpe": row["sharpe_proxy"],
                        "max_drawdown": row["max_drawdown"],
                    }
                    for row in scored[:5]
                ],
                "no_lookahead_note": "Selection used training data ending before rebalance date.",
            }
        )

        for date, ret in hold.items():
            prev = equity
            equity = equity * (1.0 + float(ret))
            curve.append(
                {
                    "date": pd.Timestamp(date).date().isoformat(),
                    "strategy_id": active_strategy,
                    "daily_return": float(ret),
                    "daily_pnl": float(equity - prev),
                    "portfolio_value": float(equity),
                }
            )

    if not curve or active_strategy is None:
        raise ValueError("No simulation curve generated")

    curve_frame = pd.DataFrame(curve)
    curve_frame["date"] = pd.to_datetime(curve_frame["date"])
    curve_frame["drawdown"] = curve_frame["portfolio_value"] / curve_frame["portfolio_value"].cummax() - 1.0
    latest = curve_frame.iloc[-1]
    previous = curve_frame.iloc[-2] if len(curve_frame) >= 2 else latest
    total_return = float(latest["portfolio_value"] / initial_capital - 1.0)
    current_rets = active_rets[active_rets.index <= curve_frame["date"].max()].tail(60)
    daily_mean = float(current_rets.mean()) if not current_rets.empty else 0.0
    daily_vol = float(current_rets.std(ddof=0)) if len(current_rets) > 1 else 0.0
    current_config = strategy_configs[active_strategy]
    latest_prices = close.loc[close.index <= curve_frame["date"].max()].iloc[-1]
    sleeve_weight = 1.0 / len(current_config["target_etfs"]) if current_config["target_etfs"] else 0.0
    current_holdings = []
    for ticker in current_config["target_etfs"]:
        current_holdings.append(
            {
                "ticker": ticker,
                "sleeve_weight": sleeve_weight,
                "market_value": float(latest["portfolio_value"] * sleeve_weight),
                "latest_close": float(latest_prices[ticker]) if ticker in latest_prices and pd.notna(latest_prices[ticker]) else None,
            }
        )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "data_mode": "no_lookahead_strategy_guided_portfolio_simulation",
        "official_risk_decision_allowed": False,
        "initial_capital": initial_capital,
        "simulation_start_requested": start_date,
        "simulation_start_actual": curve[0]["date"],
        "as_of_date": pd.Timestamp(latest["date"]).date().isoformat(),
        "price_path": str(Path(price_path).resolve()),
        "train_years": train_years,
        "rebalance_frequency": "monthly_first_trading_day",
        "selection_rule": (
            "Monthly strategy selection ranks candidates using only prior 5-year data. "
            "Conservative score weights Sharpe, drawdown, total return, monthly win rate, and volatility."
        ),
        "current": {
            "portfolio_value": float(latest["portfolio_value"]),
            "previous_value": float(previous["portfolio_value"]),
            "daily_pnl": float(latest["portfolio_value"] - previous["portfolio_value"]),
            "daily_return": float(latest["portfolio_value"] / previous["portfolio_value"] - 1.0),
            "total_return": total_return,
            "max_drawdown": float(curve_frame["drawdown"].min()),
            "current_strategy": active_strategy,
            "current_strategy_name": current_config["strategy_name"],
            "current_strategy_objective": current_config["objective"],
            "core_signal": current_config["core_signal"],
            "risk_controls": current_config["risk_controls"],
        },
        "tomorrow_preview": {
            "base_case_daily_return": daily_mean,
            "one_sigma_downside": daily_mean - daily_vol,
            "one_sigma_upside": daily_mean + daily_vol,
            "expected_daily_pnl": float(latest["portfolio_value"] * daily_mean),
            "downside_daily_pnl": float(latest["portfolio_value"] * (daily_mean - daily_vol)),
            "upside_daily_pnl": float(latest["portfolio_value"] * (daily_mean + daily_vol)),
            "interpretation": (
                "This is a statistical preview from recent selected-sleeve returns, "
                "not a forecast or trading instruction."
            ),
            "watch_items": [
                "Confirm whether current sleeve ETFs continue to support the selected strategy.",
                "Check news linkage and risk limit utilization before any rebalance.",
                "Escalate only if market moves, news, and portfolio risk limits agree.",
            ],
        },
        "current_holdings": current_holdings,
        "selection_log": selection_log,
        "equity_curve": curve_frame.assign(date=curve_frame["date"].dt.strftime("%Y-%m-%d")).to_dict(orient="records"),
        "note": "Simulation support only. No execution, no investment advice, no look-ahead selection.",
    }
    return _json_safe(payload)


def main() -> None:
    payload = build_strategy_simulation()
    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
    cur = payload["current"]
    print(f"output: {DEFAULT_OUTPUT_PATH}")
    print(f"start: {payload['simulation_start_actual']} as_of: {payload['as_of_date']}")
    print(f"portfolio_value: {cur['portfolio_value']:.2f}")
    print(f"total_return: {cur['total_return']:.4f}")
    print(f"current_strategy: {cur['current_strategy']}")
    print(f"selection_events: {len(payload['selection_log'])}")


if __name__ == "__main__":
    main()
