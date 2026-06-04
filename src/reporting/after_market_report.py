"""
After-market risk manager memo (prototype).

What: Assemble metrics, rule alerts, holdings, and factor attribution into a daily memo.
Why: Answer what happened, why it matters, and what to monitor next - not trading advice.
Inputs: Sample prices and configs through as_of_date only (no look-ahead).
Outputs: Structured report dict and Markdown file under reports/generated/.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.config_loader import PROJECT_ROOT, load_all_configs
from src.factors.factor_model import build_factor_snapshot
from src.portfolio.metrics_builder import (
    COMPUTED_DATA_SOURCE,
    build_metrics_snapshot,
    snapshot_to_jsonable,
)
from src.regime.metric_status import derive_metric_statuses, get_metric_status_summary
from src.regime.rule_engine import (
    RED_INFORMATIONAL_DISCLAIMER,
    derive_informational_context_note,
    escalation_basis_alerts,
    get_informational_context_display,
    run_rule_engine,
    subsumed_alert_explanation,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "generated"
SAMPLE_OR_LIVE_LABEL = "sample_replay_prototype"
NO_LOOKAHEAD_STATEMENT = (
    "All inputs are computed from data available on or before as_of_date only."
)

FORBIDDEN_PHRASES = (
    "buy ",
    "sell ",
    "execute ",
    "trade now",
    "guaranteed",
)

REQUIRED_SECTIONS = (
    "metadata",
    "executive_risk_summary",
    "market_close_snapshot",
    "metric_status_view",
    "portfolio_risk_readout",
    "factor_risk_view",
    "strategy_alert_view",
    "next_day_watchlist",
    "governance_notes",
)

MARKDOWN_HEADINGS = (
    "# After-Market Risk Report",
    "## Executive Risk Summary",
    "## 1. Market Close Snapshot",
    "## 2. Portfolio Risk Readout",
    "## 3. Factor Risk View",
    "## 4. Strategy & Alert View",
    "## 5. Next Trading Day Watchlist",
    "## 6. Governance and No-Look-Ahead Notes",
)


def _fmt_pct(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def _metric(metrics: dict[str, Any], key: str) -> float | int | None:
    val = metrics.get(key)
    if val is None:
        return None
    return float(val) if isinstance(val, (int, float)) else val


def _interpret_vix_level(level: float | None) -> str:
    if level is None:
        return "VIX level unavailable; flag for data review."
    if level >= 30:
        return "Elevated implied volatility; monitor risk appetite and hedging needs."
    if level >= 20:
        return "Moderate implied volatility; watch for further risk-off confirmation."
    return "Subdued implied volatility versus stress regimes; still monitor tail risks."


def _interpret_vix_change(change: float | None) -> str:
    if change is None:
        return "VIX change unavailable; flag for data review."
    if change > 2:
        return "Sharp rise in fear gauge; flag cross-asset stress confirmation."
    if change > 0.5:
        return "Rising volatility; monitor defensive sleeves and credit spreads."
    if change < -1:
        return "Volatility easing; confirm whether risk-on is broad or narrow."
    return "Muted VIX move; continue monitoring macro and credit signals."


def _interpret_return(ret: float | None, label: str) -> str:
    if ret is None:
        return f"{label} return unavailable."
    if ret <= -0.02:
        return f"{label} under pressure over the lookback window; flag for portfolio review."
    if ret < 0:
        return f"{label} slightly negative; monitor continuation."
    if ret >= 0.02:
        return f"{label} firm over the lookback window; monitor concentration risk."
    return f"{label} move modest; continue standard monitoring."


def _interpret_credit_rel(rel: float | None) -> str:
    if rel is None:
        return "Credit relative move unavailable."
    if rel < -0.005:
        return "HY underperforming IG; credit stress proxy warrants heightened review."
    if rel > 0.005:
        return "HY outperforming IG; risk appetite may be improving - confirm breadth."
    return "Credit relative move contained; continue spread monitoring."


def _derive_overall_escalation(alerts: pd.DataFrame) -> str:
    if alerts.empty:
        return "green"
    levels = set(alerts["escalation_level"].astype(str).str.lower())
    if "red" in levels:
        return "red"
    if "yellow" in levels:
        return "yellow"
    return "green"


def _human_review_count(alerts: pd.DataFrame) -> int:
    if alerts.empty:
        return 0
    return int(alerts["requires_human_review"].sum())


def _alerts_to_records(alerts: pd.DataFrame) -> list[dict[str, Any]]:
    if alerts.empty:
        return []
    return alerts.to_dict(orient="records")


def _unique_strategies_from_alerts(alerts: pd.DataFrame) -> list[str]:
    if alerts.empty:
        return []
    strategies: set[str] = set()
    for raw in alerts["affected_strategies"].astype(str):
        for part in raw.split(";"):
            part = part.strip()
            if part:
                strategies.add(part)
    return sorted(strategies)


def _recommended_review_actions(alerts: pd.DataFrame) -> list[str]:
    if alerts.empty:
        return ["No rule alerts triggered; maintain standard monitoring cadence."]
    actions: list[str] = []
    for _, row in alerts.iterrows():
        actions.append(
            f"[{row['escalation_level'].upper()}] {row['rule_id']}: "
            f"{row['recommended_action']} (requires human review: "
            f"{'yes' if row['requires_human_review'] else 'no'})"
        )
    return actions


def _exposure_table(holdings: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    grouped = (
        holdings.groupby(column, as_index=False)["target_weight"]
        .sum()
        .sort_values("target_weight", ascending=False)
    )
    return [
        {column: row[column], "target_weight": float(row["target_weight"])}
        for _, row in grouped.iterrows()
    ]


def _run_rule_engine_for_snapshot(
    snapshot: dict[str, Any],
    config_dir: Path | str | None,
) -> dict[str, Any]:
    payload = snapshot_to_jsonable(snapshot)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(payload, handle)
            tmp_path = Path(handle.name)
        return run_rule_engine(metrics_path=tmp_path, config_dir=config_dir)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _build_market_close_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    spy_ret = _metric(metrics, "SPY return")
    hyg_lqd = _metric(metrics, "HYG vs LQD relative return")
    return {
        "VIX level": {
            "value": _metric(metrics, "VIX level"),
            "interpretation": _interpret_vix_level(_metric(metrics, "VIX level")),
        },
        "VIX change": {
            "value": _metric(metrics, "VIX change"),
            "interpretation": _interpret_vix_change(_metric(metrics, "VIX change")),
        },
        "SPY return": {
            "value": spy_ret,
            "interpretation": _interpret_return(spy_ret, "SPY"),
        },
        "QQQ return": {"value": _metric(metrics, "QQQ return")},
        "IWM return": {"value": _metric(metrics, "IWM return")},
        "TLT return": {"value": _metric(metrics, "TLT return")},
        "HYG return": {"value": _metric(metrics, "HYG return")},
        "LQD return": {"value": _metric(metrics, "LQD return")},
        "HYG vs LQD relative return": {
            "value": hyg_lqd,
            "interpretation": _interpret_credit_rel(hyg_lqd),
        },
        "GLD return": {"value": _metric(metrics, "GLD return")},
        "UUP return": {"value": _metric(metrics, "UUP return")},
        "USO return": {"value": _metric(metrics, "USO return")},
    }


def _build_factor_risk_view(factor_df: pd.DataFrame) -> dict[str, Any]:
    pos = (
        factor_df.nlargest(5, "contribution_to_return")[
            ["factor_id", "factor_name", "contribution_to_return", "interpretation"]
        ]
        .to_dict(orient="records")
    )
    neg = (
        factor_df.nsmallest(5, "contribution_to_return")[
            ["factor_id", "factor_name", "contribution_to_return", "interpretation"]
        ]
        .to_dict(orient="records")
    )
    largest = (
        factor_df.nlargest(5, "exposure")[
            ["factor_id", "factor_name", "proxy_ticker", "exposure"]
        ]
        .to_dict(orient="records")
    )
    return {
        "top_positive_factor_contributions": pos,
        "top_negative_factor_contributions": neg,
        "largest_exposure_factors": largest,
        "interpretation": (
            "Observable ETF proxy attribution over a short lookback: factor exposure "
            "equals benchmark weight when the proxy ETF is held. This is not a Barra "
            "or commercial factor model; correlated proxies may overlap."
        ),
    }


def _build_next_day_watchlist(
    metrics: dict[str, Any],
    alerts: pd.DataFrame,
    factor_df: pd.DataFrame,
    strategies: pd.DataFrame,
) -> dict[str, Any]:
    risk_factors = [
        "VIX level and change versus recent range",
        "SPY and QQQ short-horizon returns for beta sleeve confirmation",
        "HYG vs LQD relative return for credit stress proxy",
        "Portfolio drawdown and VaR ratio versus policy thresholds",
    ]
    top_factor = factor_df.nlargest(1, "contribution_to_return")
    if not top_factor.empty:
        fid = top_factor.iloc[0]["factor_id"]
        risk_factors.append(f"Largest positive proxy contribution: {fid}")

    escalate: list[str] = []
    if _metric(metrics, "VIX change") and _metric(metrics, "VIX change") > 2:
        escalate.append("Further VIX rise with cross-asset confirmation would escalate to yellow/red review.")
    if _metric(metrics, "portfolio drawdown") and _metric(metrics, "portfolio drawdown") < -0.05:
        escalate.append("Deeper portfolio drawdown would escalate defensive review.")
    if not alerts.empty:
        escalate.append(
            "Additional threshold hits on linked rules would increase alert count and escalation."
        )
    if not escalate:
        escalate.append(
            "Sustained deterioration in credit proxy or volatility would flag for escalation."
        )

    defensive = []
    if not alerts.empty:
        for sid in _unique_strategies_from_alerts(alerts):
            match = strategies[strategies["strategy_id"] == sid]
            if not match.empty:
                defensive.append(
                    f"{sid}: {match.iloc[0]['dashboard_action_label']} "
                    f"(propose defensive review; human review required)."
                )
    if not defensive:
        defensive.append(
            "defensive_rotation and credit_stress_defense remain standing review candidates if stress builds."
        )

    data_news = [
        "Sample synthetic price replay only until live feeds are wired.",
        "Headline severity placeholder remains zero in prototype metrics.",
        "Cross-asset confirmation count and credit relative return.",
    ]

    human_items: list[str] = []
    if not alerts.empty:
        for _, row in alerts.iterrows():
            if row["requires_human_review"]:
                human_items.append(
                    f"{row['rule_id']}: {row['recommended_action']}"
                )
    if not human_items:
        human_items.append("No human-review-required alerts today; maintain governance cadence.")

    return {
        "risk_factors_to_monitor": risk_factors,
        "conditions_that_would_escalate": escalate,
        "defensive_review_candidates": defensive,
        "data_or_news_to_watch": data_news,
        "human_approval_required_items": human_items,
    }


def _build_executive_summary(
    metrics: dict[str, Any],
    alerts: pd.DataFrame,
    factor_df: pd.DataFrame,
    watchlist: dict[str, Any],
    informational_alerts: pd.DataFrame | None = None,
) -> dict[str, Any]:
    escalation = _derive_overall_escalation(alerts)
    review_count = _human_review_count(alerts)

    vix = _metric(metrics, "VIX level")
    spy = _metric(metrics, "SPY return")
    p_dd = _metric(metrics, "portfolio drawdown")
    p_var = _metric(metrics, "portfolio VaR")
    credit = _metric(metrics, "HYG vs LQD relative return")

    if escalation == "red":
        headline = "Risk posture elevated: red escalation alerts require immediate human review."
    elif escalation == "yellow":
        headline = "Heightened monitoring: yellow escalation alerts flagged for defensive review."
    else:
        headline = "Baseline monitoring: no yellow or red escalation alerts on this replay date."

    main_market = (
        f"VIX {vix:.2f} with {_fmt_pct(spy)} SPY lookback return; "
        f"{_interpret_vix_level(vix).split(';')[0]}."
        if vix is not None and spy is not None
        else "Market snapshot incomplete; verify price replay."
    )

    main_portfolio = (
        f"Portfolio drawdown {_fmt_pct(p_dd)} and VaR ratio {p_var:.3f}."
        if p_dd is not None and p_var is not None
        else "Portfolio risk metrics unavailable for this date."
    )

    top_contrib = factor_df.nlargest(1, "contribution_to_return")
    if top_contrib.empty:
        main_factor = "Factor attribution unavailable."
    else:
        row = top_contrib.iloc[0]
        main_factor = (
            f"Largest proxy contribution: {row['factor_id']} "
            f"({_fmt_pct(row['contribution_to_return'], 3)} over lookback)."
        )

    if alerts.empty:
        if informational_alerts is not None and not informational_alerts.empty:
            main_strategy = (
                "No actionable rule alerts; informational context only."
            )
        else:
            main_strategy = (
                "No regime rule alerts; strategy library remains in standard watch mode."
            )
    else:
        main_strategy = (
            f"{len(alerts)} actionable rule alert(s); "
            f"{review_count} require human review."
        )

    watch_summary = "; ".join(watchlist["risk_factors_to_monitor"][:3])

    return {
        "overall_escalation_level": escalation,
        "headline_summary": headline,
        "main_market_message": main_market,
        "main_portfolio_risk": main_portfolio,
        "main_factor_pressure": main_factor,
        "main_strategy_concern": main_strategy,
        "tomorrow_watchlist_summary": watch_summary,
        "human_review_required_count": review_count,
    }


def _build_metric_status_view(
    metrics: dict[str, Any],
    policy_df: pd.DataFrame,
) -> dict[str, Any]:
    """Build metric-level status table and summary (not rule alerts)."""
    status_df = derive_metric_statuses(metrics, policy_df)
    summary = get_metric_status_summary(status_df)
    return {
        "metric_status_table": status_df.to_dict(orient="records"),
        "green_count": summary["green_count"],
        "yellow_count": summary["yellow_count"],
        "red_count": summary["red_count"],
        "missing_count": summary["missing_count"],
        "missing_metrics": summary["missing_metrics"],
        "yellow_metrics": summary["yellow_metrics"],
        "red_metrics": summary["red_metrics"],
        "green_metrics": summary["green_metrics"],
        "explanation": (
            "Metric-level status identifies individual pressure points; "
            "final escalation depends on rule confirmation."
        ),
    }


def _build_governance_notes() -> dict[str, Any]:
    return {
        "sample_replay_prototype_only": True,
        "no_live_api": True,
        "no_execution": True,
        "no_investment_recommendation": True,
        "no_backtest_performance_claim": True,
        "no_look_ahead": NO_LOOKAHEAD_STATEMENT,
        "human_review_required_for_proposed_actions": True,
        "bullets": [
            "Sample replay / prototype only - not live Bloomberg or OpenBB feeds.",
            "No trade execution pathway in this repository.",
            "Not investment advice; proposed actions require human review.",
            "No backtest or walk-forward performance claims in this memo.",
            NO_LOOKAHEAD_STATEMENT,
            "Rule-engine outputs are monitoring proposals, not automated instructions.",
        ],
    }


def _build_strategy_alert_view(
    alerts: pd.DataFrame,
    primary_alerts: pd.DataFrame,
    subsumed_alerts: pd.DataFrame,
    informational_alerts: pd.DataFrame,
    informational_context_mode: str,
    informational_context_note: str,
    red_alerts: pd.DataFrame,
    yellow_alerts: pd.DataFrame,
) -> dict[str, Any]:
    basis = escalation_basis_alerts(primary_alerts, alerts)
    escalation = _derive_overall_escalation(basis)
    stress_disclaimer: str | None = None
    if (
        escalation == "red"
        and not informational_alerts.empty
    ):
        stress_disclaimer = RED_INFORMATIONAL_DISCLAIMER

    subsumed_notes: list[str] = []
    if not subsumed_alerts.empty:
        for _, row in subsumed_alerts.iterrows():
            subsumed_notes.append(
                subsumed_alert_explanation(
                    str(row["rule_id"]),
                    str(row["subsumed_by"]),
                )
            )

    return {
        "triggered_alerts": _alerts_to_records(alerts),
        "primary_actionable_alerts": _alerts_to_records(primary_alerts),
        "subsumed_actionable_alerts": _alerts_to_records(subsumed_alerts),
        "subsumed_alert_notes": subsumed_notes,
        "informational_context_alerts": _alerts_to_records(informational_alerts),
        "informational_context_mode": informational_context_mode,
        "informational_context_note": informational_context_note,
        "informational_stress_disclaimer": stress_disclaimer,
        "red_alerts": _alerts_to_records(red_alerts),
        "yellow_alerts": _alerts_to_records(yellow_alerts),
        "affected_strategies": _unique_strategies_from_alerts(basis),
        "recommended_review_actions": _recommended_review_actions(basis),
        "human_review_required_count": _human_review_count(basis),
    }


def build_after_market_report(
    as_of_date: str | None = None,
    price_path: Path | str | None = None,
    config_dir: Path | str | None = None,
    expected_source: str | None = "sample_synthetic",
    sample_or_live_label: str = SAMPLE_OR_LIVE_LABEL,
) -> dict[str, Any]:
    """
    Build structured after-market risk memo for risk managers.

    All inputs respect as_of_date (no look-ahead).
    """
    configs = load_all_configs(config_dir)
    snapshot = build_metrics_snapshot(
        price_path=price_path,
        config_dir=config_dir,
        as_of_date=as_of_date,
        expected_source=expected_source,
    )
    metrics = snapshot["metrics"]
    resolved_as_of = snapshot["as_of_date"]

    engine = _run_rule_engine_for_snapshot(snapshot, config_dir)
    alerts = engine["alerts"]
    primary_alerts = engine.get("primary_alerts", alerts)
    subsumed_alerts = engine.get(
        "subsumed_alerts",
        alerts.iloc[0:0].copy() if hasattr(alerts, "iloc") else alerts,
    )
    basis = escalation_basis_alerts(primary_alerts, alerts)
    informational_alerts = engine["informational_alerts"]
    informational_context_mode = engine.get(
        "informational_context_mode", "normal_context"
    )
    has_informational_context = not informational_alerts.empty
    informational_context_note = engine.get(
        "informational_context_note",
        derive_informational_context_note(
            informational_context_mode,
            has_informational_context,
        ),
    )
    factor_df = build_factor_snapshot(
        price_path=price_path,
        config_dir=config_dir,
        as_of_date=resolved_as_of,
        expected_source=expected_source,
    )

    holdings = configs["holdings"]
    strategies = configs["strategy_library"]

    watchlist = _build_next_day_watchlist(metrics, basis, factor_df, strategies)
    executive = _build_executive_summary(
        metrics, basis, factor_df, watchlist, informational_alerts
    )

    red_alerts = (
        basis[basis["escalation_level"] == "red"] if not basis.empty else basis
    )
    yellow_alerts = (
        basis[basis["escalation_level"] == "yellow"] if not basis.empty else basis
    )

    report = {
        "metadata": {
            "as_of_date": resolved_as_of,
            "data_source": snapshot.get("data_source", COMPUTED_DATA_SOURCE),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "sample_or_live_label": sample_or_live_label,
            "no_look_ahead_statement": NO_LOOKAHEAD_STATEMENT,
        },
        "executive_risk_summary": executive,
        "market_close_snapshot": _build_market_close_snapshot(metrics),
        "metric_status_view": _build_metric_status_view(
            metrics, configs["metric_status_policy"]
        ),
        "portfolio_risk_readout": {
            "portfolio drawdown": _metric(metrics, "portfolio drawdown"),
            "portfolio VaR ratio": _metric(metrics, "portfolio VaR"),
            "SPY drawdown": _metric(metrics, "SPY drawdown"),
            "credit stress proxy": _metric(metrics, "HYG vs LQD relative return"),
            "cross-asset confirmation count": _metric(
                metrics, "cross-asset confirmation count"
            ),
            "exposure_by_asset_class": _exposure_table(holdings, "asset_class"),
            "exposure_by_risk_bucket": _exposure_table(holdings, "risk_bucket"),
        },
        "factor_risk_view": _build_factor_risk_view(factor_df),
        "strategy_alert_view": _build_strategy_alert_view(
            alerts,
            primary_alerts,
            subsumed_alerts,
            informational_alerts,
            informational_context_mode,
            informational_context_note,
            red_alerts,
            yellow_alerts,
        ),
        "next_day_watchlist": watchlist,
        "governance_notes": _build_governance_notes(),
    }

    for section in REQUIRED_SECTIONS:
        if section not in report:
            raise ValueError(f"report missing section: {section}")

    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render intuitive Markdown memo for risk managers."""
    meta = report["metadata"]
    exe = report["executive_risk_summary"]
    mkt = report["market_close_snapshot"]
    mstat = report["metric_status_view"]
    port = report["portfolio_risk_readout"]
    factor = report["factor_risk_view"]
    strat = report["strategy_alert_view"]
    watch = report["next_day_watchlist"]
    gov = report["governance_notes"]

    lines: list[str] = [
        MARKDOWN_HEADINGS[0],
        "",
        f"**As of:** {meta['as_of_date']}  ",
        f"**Data source:** {meta['data_source']}  ",
        f"**Generated (UTC):** {meta['generated_at']}  ",
        f"**Mode:** {meta['sample_or_live_label']}  ",
        "",
        MARKDOWN_HEADINGS[1],
        "",
        f"- **Overall escalation:** {exe['overall_escalation_level'].upper()}",
        f"- **Headline:** {exe['headline_summary']}",
        f"- **Market:** {exe['main_market_message']}",
        f"- **Portfolio risk:** {exe['main_portfolio_risk']}",
        f"- **Factor pressure:** {exe['main_factor_pressure']}",
        f"- **Strategy / alerts:** {exe['main_strategy_concern']}",
        f"- **Watchlist focus:** {exe['tomorrow_watchlist_summary']}",
        f"- **Human review required (alerts):** {exe['human_review_required_count']}",
        "",
        MARKDOWN_HEADINGS[2],
        "",
        f"- **VIX level:** {mkt['VIX level']['value']} - {mkt['VIX level']['interpretation']}",
        f"- **VIX change:** {mkt['VIX change']['value']} - {mkt['VIX change']['interpretation']}",
        f"- **SPY return:** {_fmt_pct(mkt['SPY return']['value'])} - {mkt['SPY return']['interpretation']}",
        f"- **QQQ return:** {_fmt_pct(mkt['QQQ return']['value'])}",
        f"- **IWM return:** {_fmt_pct(mkt['IWM return']['value'])}",
        f"- **TLT return:** {_fmt_pct(mkt['TLT return']['value'])}",
        f"- **HYG return:** {_fmt_pct(mkt['HYG return']['value'])}",
        f"- **LQD return:** {_fmt_pct(mkt['LQD return']['value'])}",
        f"- **HYG vs LQD relative:** {_fmt_pct(mkt['HYG vs LQD relative return']['value'])} - "
        f"{mkt['HYG vs LQD relative return']['interpretation']}",
        f"- **GLD return:** {_fmt_pct(mkt['GLD return']['value'])}",
        f"- **UUP return:** {_fmt_pct(mkt['UUP return']['value'])}",
        f"- **USO return:** {_fmt_pct(mkt['USO return']['value'])}",
        "",
        "### Metric Status Summary",
        "",
        f"- **Green metrics:** {mstat['green_count']}",
        f"- **Yellow metrics:** {mstat['yellow_count']}",
        f"- **Red metrics:** {mstat['red_count']}",
        f"- **Yellow list:** {', '.join(mstat['yellow_metrics']) or 'none'}",
        f"- **Red list:** {', '.join(mstat['red_metrics']) or 'none'}",
        f"- **Missing metrics:** {mstat['missing_count']} "
        f"({', '.join(mstat['missing_metrics']) or 'none'})",
        f"- _{mstat['explanation']}_",
        "",
        MARKDOWN_HEADINGS[3],
        "",
        f"- **Portfolio drawdown:** {_fmt_pct(port['portfolio drawdown'])}",
        f"- **Portfolio VaR ratio:** {port['portfolio VaR ratio']}",
        f"- **SPY drawdown:** {_fmt_pct(port['SPY drawdown'])}",
        f"- **Credit stress proxy (HYG vs LQD rel):** {_fmt_pct(port['credit stress proxy'])}",
        f"- **Cross-asset confirmation count:** {port['cross-asset confirmation count']}",
        "",
        "**Exposure by asset_class**",
    ]
    for row in port["exposure_by_asset_class"]:
        lines.append(f"- {row['asset_class']}: {row['target_weight']:.2%}")
    lines.extend(["", "**Exposure by risk_bucket**"])
    for row in port["exposure_by_risk_bucket"]:
        lines.append(f"- {row['risk_bucket']}: {row['target_weight']:.2%}")

    lines.extend(
        [
            "",
            MARKDOWN_HEADINGS[4],
            "",
            f"_{factor['interpretation']}_",
            "",
            "**Top positive proxy contributions**",
        ]
    )
    for row in factor["top_positive_factor_contributions"]:
        lines.append(
            f"- {row['factor_id']}: {_fmt_pct(row['contribution_to_return'], 3)}"
        )
    lines.append("")
    lines.append("**Top negative proxy contributions**")
    for row in factor["top_negative_factor_contributions"]:
        lines.append(
            f"- {row['factor_id']}: {_fmt_pct(row['contribution_to_return'], 3)}"
        )
    lines.append("")
    lines.append("**Largest proxy exposures (held weights)**")
    for row in factor["largest_exposure_factors"]:
        lines.append(f"- {row['factor_id']}: {row['exposure']:.2%} ({row['proxy_ticker']})")

    lines.extend(
        [
            "",
            MARKDOWN_HEADINGS[5],
            "",
            f"- **Primary actionable alerts:** {len(strat['primary_actionable_alerts'])}",
            f"- **Subsumed context alerts:** {len(strat['subsumed_actionable_alerts'])}",
            f"- **Full actionable audit (yellow/red):** {len(strat['triggered_alerts'])}",
            f"- **Red alerts (primary basis):** {len(strat['red_alerts'])}",
            f"- **Yellow alerts (primary basis):** {len(strat['yellow_alerts'])}",
            f"- **Human review required:** {strat['human_review_required_count']}",
        ]
    )
    if strat["affected_strategies"]:
        lines.append(f"- **Affected strategies:** {', '.join(strat['affected_strategies'])}")
    lines.append("")
    lines.append("**Primary actionable alerts**")
    if strat["primary_actionable_alerts"]:
        for row in strat["primary_actionable_alerts"]:
            lines.append(
                f"- [{row['escalation_level'].upper()}] {row['rule_id']}: "
                f"{row.get('recommended_action', 'monitor')}"
            )
    else:
        lines.append("- (none)")
    subsumed_rows = strat.get("subsumed_actionable_alerts", [])
    if subsumed_rows:
        lines.append("")
        lines.append("**Subsumed context alerts**")
        notes = strat.get("subsumed_alert_notes", [])
        for idx, row in enumerate(subsumed_rows):
            lines.append(
                f"- [{row['escalation_level'].upper()}] {row['rule_id']}: "
                f"{row.get('recommended_action', 'monitor')}"
            )
            if idx < len(notes):
                lines.append(f"  - _{notes[idx]}_")
    lines.append("")
    lines.append("**Recommended review actions (primary basis)**")
    for action in strat["recommended_review_actions"]:
        lines.append(f"- {action}")
    info_alerts = strat.get("informational_context_alerts", [])
    if info_alerts:
        mode = strat.get("informational_context_mode", "normal_context")
        has_info = bool(info_alerts)
        display = get_informational_context_display(mode, has_info)
        lines.append("")
        lines.append(f"### {display['section_title']}")
        lines.append("")
        lines.append(f"**Context mode:** `{mode}`")
        lines.append("")
        lines.append(f"_{strat.get('informational_context_note', display['caption'])}_")
        disclaimer = strat.get("informational_stress_disclaimer")
        if disclaimer:
            lines.append("")
            lines.append(f"_{disclaimer}_")
        lines.append("")
        lines.append(
            "_Green informational rules below are not action triggers and do not "
            "drive escalation or human review._"
        )
        for row in info_alerts:
            lines.append(
                f"- {row['rule_id']}: {row.get('recommended_action', 'monitor')}"
            )

    lines.extend(["", MARKDOWN_HEADINGS[6], ""])
    for item in watch["risk_factors_to_monitor"]:
        lines.append(f"- Monitor: {item}")
    lines.append("")
    lines.append("**Conditions that would escalate review**")
    for item in watch["conditions_that_would_escalate"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("**Defensive review candidates**")
    for item in watch["defensive_review_candidates"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("**Data / news to watch**")
    for item in watch["data_or_news_to_watch"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("**Human approval required**")
    for item in watch["human_approval_required_items"]:
        lines.append(f"- {item}")

    lines.extend(["", MARKDOWN_HEADINGS[7], ""])
    for bullet in gov["bullets"]:
        lines.append(f"- {bullet}")

    text = "\n".join(lines) + "\n"
    lowered = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            raise ValueError(f"report contains forbidden phrase: {phrase!r}")
    return text


def write_after_market_report(
    output_dir: Path | str | None = None,
    as_of_date: str | None = None,
    price_path: Path | str | None = None,
    config_dir: Path | str | None = None,
    expected_source: str | None = "sample_synthetic",
    sample_or_live_label: str = SAMPLE_OR_LIVE_LABEL,
) -> Path:
    """Write Markdown after-market report to reports/generated/."""
    report = build_after_market_report(
        as_of_date=as_of_date,
        price_path=price_path,
        config_dir=config_dir,
        expected_source=expected_source,
        sample_or_live_label=sample_or_live_label,
    )
    md = render_markdown_report(report)
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = report["metadata"]["as_of_date"]
    out_path = out_dir / f"after_market_risk_report_{as_of}.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path
