"""Friend/API news monitor and risk translator.

Turns raw headlines into risk-manager context. This is not NLP alpha; it is a
governance layer that classifies headline severity and maps topics to strategy
review candidates.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any

CRITICAL_KEYWORDS = {
    "war",
    "attack",
    "missile",
    "sanction",
    "default",
    "bankruptcy",
    "invasion",
    "terror",
    "emergency",
    "fed surprise",
}
HIGH_KEYWORDS = {
    "inflation",
    "oil",
    "credit",
    "liquidity",
    "downgrade",
    "tariff",
    "election",
    "shutdown",
    "recession",
}

TOPIC_STRATEGY_MAP = {
    "fed-rates": ["real_rates_duration_sleeve", "risk_parity_etf_sleeve"],
    "credit-stress": ["credit_stress_defensive_overlay", "credit_risk_premium_sleeve"],
    "tariffs": ["usd_liquidity_stress_sleeve", "inflation_protection_sleeve"],
    "bank-crisis": ["credit_stress_defensive_overlay", "liquidity_first_defensive_portfolio"],
    "etf-flows": ["factor_completion_portfolio", "low_cost_factor_replication"],
    "geopolitical": ["gold_geopolitical_hedge_sleeve", "usd_liquidity_stress_sleeve"],
    "war": ["gold_geopolitical_hedge_sleeve", "energy_inflation_shock_rotation"],
    "oil": ["energy_inflation_shock_rotation", "inflation_protection_sleeve"],
    "inflation": ["inflation_protection_sleeve", "real_rates_duration_sleeve"],
    "rates": ["real_rates_duration_sleeve", "risk_parity_etf_sleeve"],
    "credit": ["credit_stress_defensive_overlay", "credit_risk_premium_sleeve"],
    "liquidity": ["liquidity_first_defensive_portfolio", "usd_liquidity_stress_sleeve"],
    "usd": ["usd_liquidity_stress_sleeve", "factor_completion_portfolio"],
    "technology": ["quality_factor_sleeve", "economic_growth_beta_sleeve"],
    "macro": ["economic_growth_beta_sleeve", "multi_factor_smart_beta_sleeve"],
}

TOPIC_ASSET_MAP = {
    "fed-rates": ["Fixed Income", "FX"],
    "rates": ["Fixed Income", "FX"],
    "inflation": ["Fixed Income", "Commodity"],
    "oil": ["Commodity", "Equity"],
    "war": ["Commodity", "FX"],
    "geopolitical": ["Commodity", "FX"],
    "credit-stress": ["Fixed Income"],
    "credit": ["Fixed Income"],
    "liquidity": ["Fixed Income", "FX"],
    "bank-crisis": ["Fixed Income", "Equity"],
    "tariffs": ["Equity", "Commodity", "FX"],
    "usd": ["FX", "International Equity"],
    "technology": ["Equity"],
    "macro": ["Equity", "Fixed Income"],
}

TOPIC_TICKER_MAP = {
    "fed-rates": ["TLT", "IEF", "SHY", "TIP", "UUP"],
    "rates": ["TLT", "IEF", "SHY", "TIP", "UUP"],
    "inflation": ["TIP", "GLD", "USO", "XLE"],
    "oil": ["USO", "XLE"],
    "war": ["GLD", "USO", "XLE", "UUP"],
    "geopolitical": ["GLD", "USO", "UUP"],
    "credit-stress": ["HYG", "LQD", "EMB"],
    "credit": ["HYG", "LQD", "EMB"],
    "liquidity": ["SHY", "UUP", "HYG"],
    "bank-crisis": ["HYG", "LQD", "XLF", "SHY"],
    "tariffs": ["UUP", "XLI", "XLB", "XLE"],
    "usd": ["UUP", "EFA", "EEM"],
    "technology": ["QQQ", "XLK"],
    "macro": ["SPY", "QQQ", "TLT"],
}

TOPIC_PATTERNS = {
    "fed-rates": [r"\bfed\b", r"\bfomc\b", r"\brate\s+cut\b", r"\brate\s+hike\b", r"\bcentral\s+bank\b"],
    "credit-stress": [r"\bcredit\s+stress\b", r"\bspread[s]?\s+widen", r"\bdefault\b", r"\bdowngrade\b"],
    "bank-crisis": [r"\bbank\s+crisis\b", r"\bbank\s+run\b", r"\bbankruptcy\b"],
    "tariffs": [r"\btariff[s]?\b", r"\btrade\s+war\b"],
    "geopolitical": [r"\bgeopolitical\b", r"\bsanction[s]?\b", r"\binvasion\b", r"\bmissile\b", r"\battack\b"],
    "war": [r"\bwar\b", r"\bwar-driven\b"],
    "oil": [r"\boil\b", r"\bcrude\b", r"\benergy\b"],
    "inflation": [r"\binflation\b", r"\bcpi\b", r"\bbreakeven[s]?\b"],
    "rates": [r"\brates?\b", r"\byield[s]?\b", r"\bduration\b"],
    "credit": [r"\bcredit\b", r"\bhigh\s+yield\b", r"\big\s+bond\b"],
    "liquidity": [r"\bliquidity\b", r"\bfunding\b"],
    "usd": [r"\busd\b", r"\bdollar\b", r"\bdxy\b"],
    "technology": [r"\btechnology\b", r"\bai\b", r"\bsemiconductor[s]?\b", r"\btech\b"],
    "macro": [r"\bmacro\b", r"\bgdp\b", r"\brecession\b", r"\bgrowth\b"],
    "crypto": [r"\bcrypto\b", r"\bbitcoin\b", r"\bbtc\b", r"\bethereum\b", r"\betf inflow[s]?\b"],
}

PORTFOLIO_TOPICS = set(TOPIC_STRATEGY_MAP) | {"crypto"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_friend_news(api_url: str, timeout_seconds: int = 10) -> list[dict[str, Any]]:
    """Fetch headlines from a friend/news API.

    Accepted response shapes:
    - a list of headline objects
    - {"items": [...]} or {"news": [...]} or {"articles": [...]}
    """
    request = urllib.request.Request(api_url, headers={"User-Agent": "live-strategy/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("items", "news", "articles", "data"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break
        else:
            items = [payload]
    else:
        raise ValueError("news API response must be JSON object or list")

    return [item for item in items if isinstance(item, dict)]


def fetch_friend_payload(api_url: str, timeout_seconds: int = 10) -> Any:
    """Fetch raw JSON payload from friend API."""
    request = urllib.request.Request(api_url, headers={"User-Agent": "live-strategy/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _coerce_topics(raw: Any, text: str) -> list[str]:
    topics: list[str] = []
    if isinstance(raw, list):
        topics.extend(str(x).strip().lower() for x in raw if str(x).strip())
    elif isinstance(raw, str) and raw.strip():
        topics.extend(part.strip().lower() for part in raw.split(";") if part.strip())

    lowered = text.lower()
    for topic, patterns in TOPIC_PATTERNS.items():
        if topic in topics:
            continue
        if any(re.search(pattern, lowered) for pattern in patterns):
            topics.append(topic)
    return sorted(dict.fromkeys(topics))


def _keywords(topics: list[str], text: str, limit: int = 8) -> list[str]:
    lowered = text.lower()
    keywords: list[str] = []
    for topic in topics:
        if topic in PORTFOLIO_TOPICS:
            keywords.append(topic)
    for word in sorted(CRITICAL_KEYWORDS | HIGH_KEYWORDS):
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            keywords.append(word)
    return sorted(dict.fromkeys(keywords))[:limit]


def _infer_severity(text: str, provided: Any = None) -> float:
    try:
        if provided is not None:
            return max(0.0, min(10.0, float(provided)))
    except (TypeError, ValueError):
        pass

    lowered = text.lower()
    score = 0.0
    if any(word in lowered for word in CRITICAL_KEYWORDS):
        score = max(score, 8.0)
    if any(word in lowered for word in HIGH_KEYWORDS):
        score = max(score, 6.0)
    if any(word in lowered for word in ("breaking", "urgent")):
        score += 1.0
    return max(0.0, min(10.0, score))


def _watch_level(severity: float) -> str:
    if severity >= 8:
        return "urgent_review"
    if severity >= 6:
        return "watch"
    if severity >= 3:
        return "info"
    return "low"


def _affected_strategies(topics: list[str]) -> list[str]:
    affected: list[str] = []
    for topic in topics:
        affected.extend(TOPIC_STRATEGY_MAP.get(topic, []))
    return sorted(dict.fromkeys(affected))


def _affected_asset_classes(topics: list[str]) -> list[str]:
    affected: list[str] = []
    for topic in topics:
        affected.extend(TOPIC_ASSET_MAP.get(topic, []))
    return sorted(dict.fromkeys(affected))


def _affected_tickers(topics: list[str]) -> list[str]:
    affected: list[str] = []
    for topic in topics:
        affected.extend(TOPIC_TICKER_MAP.get(topic, []))
    return sorted(dict.fromkeys(affected))


def _confidence(severity: float, topics: list[str], affected: list[str], provided: Any = None) -> float:
    try:
        if provided is not None:
            raw = float(provided)
            return max(0.0, min(1.0, raw / 100.0 if raw > 1 else raw))
    except (TypeError, ValueError):
        pass
    score = 0.25 + min(0.35, severity / 30.0)
    if topics:
        score += 0.12
    if affected:
        score += 0.18
    return round(max(0.05, min(0.95, score)), 2)


def _market_confirmations(affected_tickers: list[str], market_items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not market_items:
        return []
    by_ticker = {str(item.get("ticker", "")).upper(): item for item in market_items}
    confirmations: list[dict[str, Any]] = []
    for ticker in affected_tickers:
        row = by_ticker.get(ticker.upper())
        if not row:
            continue
        ret = row.get("latest_return_pct")
        close = row.get("latest_close")
        try:
            latest_return = float(ret)
        except (TypeError, ValueError):
            latest_return = 0.0
        try:
            latest_close = float(close)
        except (TypeError, ValueError):
            latest_close = 0.0
        confirmed = abs(latest_return) >= 0.75 or (ticker.upper() == "VIX" and latest_close >= 20)
        if confirmed:
            confirmations.append(
                {
                    "ticker": ticker.upper(),
                    "latest_return_pct": latest_return,
                    "latest_close": latest_close,
                    "reason": "large ETF move" if ticker.upper() != "VIX" else "VIX elevated",
                }
            )
    return confirmations


def _warning_level(
    *,
    severity: float,
    affected_strategies: list[str],
    affected_tickers: list[str],
    market_confirmations: list[dict[str, Any]],
) -> str:
    has_mapping = bool(affected_strategies or affected_tickers)
    has_confirmation = bool(market_confirmations)
    if severity >= 8 and has_mapping and has_confirmation:
        return "urgent"
    if severity >= 5 and has_mapping and has_confirmation:
        return "warning"
    if severity >= 5 or has_mapping:
        return "watch"
    return "info"


def _reasoning(
    *,
    topics: list[str],
    affected_strategies: list[str],
    affected_tickers: list[str],
    market_confirmations: list[dict[str, Any]],
    warning_level: str,
) -> str:
    if warning_level == "urgent":
        return "Severe headline is mapped to portfolio/strategy exposure and confirmed by affected ETF moves."
    if warning_level == "warning":
        return "Headline is portfolio-relevant and has market confirmation; prepare human review."
    if affected_strategies or affected_tickers:
        return "Headline maps to portfolio or strategy exposure, but lacks enough market confirmation for escalation."
    if "crypto" in topics:
        return "Crypto-specific headline; current ETF portfolio has no direct crypto sleeve, so treat as context unless spillover appears."
    return "No direct portfolio or strategy mapping; context only."


def _level_to_severity(level: Any, fallback: float = 0.0) -> float:
    text = str(level or "").strip().lower()
    if text in {"high", "surging"}:
        return 8.0
    if text in {"elevated", "medium", "rising"}:
        return 6.0
    if text in {"emerging", "low", "stable"}:
        return 3.0
    return fallback


def _pattern_headlines(pattern: dict[str, Any]) -> list[dict[str, Any]]:
    raw = pattern.get("headlines")
    return raw if isinstance(raw, list) else []


def _flatten_pattern_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert /analysis/patterns response into headline-like risk items."""
    items: list[dict[str, Any]] = []

    for pattern in payload.get("emergingPatterns", []) or []:
        if not isinstance(pattern, dict):
            continue
        severity = _level_to_severity(pattern.get("level"), fallback=3.0)
        topic = str(pattern.get("id") or pattern.get("name") or "macro").lower()
        for headline in _pattern_headlines(pattern) or [{}]:
            title = headline.get("title") if isinstance(headline, dict) else None
            items.append(
                {
                    "title": title or f"Emerging pattern: {pattern.get('name', topic)}",
                    "summary": f"Emerging pattern count={pattern.get('count')} level={pattern.get('level')}",
                    "source": headline.get("source") if isinstance(headline, dict) else "pattern_api",
                    "url": headline.get("link") if isinstance(headline, dict) else None,
                    "topics": [topic, str(pattern.get("category", "macro")).lower()],
                    "severity": severity,
                }
            )

    for signal in payload.get("momentumSignals", []) or []:
        if not isinstance(signal, dict):
            continue
        severity = _level_to_severity(signal.get("momentum"), fallback=5.0)
        severity = max(severity, 6.0 if float(signal.get("delta") or 0) >= 2 else 0.0)
        topic = str(signal.get("id") or signal.get("name") or "macro").lower()
        for headline in _pattern_headlines(signal) or [{}]:
            title = headline.get("title") if isinstance(headline, dict) else None
            items.append(
                {
                    "title": title or f"Momentum signal: {signal.get('name', topic)}",
                    "summary": (
                        f"Momentum={signal.get('momentum')} current={signal.get('current')} "
                        f"delta={signal.get('delta')}"
                    ),
                    "source": headline.get("source") if isinstance(headline, dict) else "pattern_api",
                    "url": headline.get("link") if isinstance(headline, dict) else None,
                    "topics": [topic, str(signal.get("category", "macro")).lower()],
                    "severity": severity,
                }
            )

    for corr in payload.get("crossSourceCorrelations", []) or []:
        if not isinstance(corr, dict):
            continue
        severity = _level_to_severity(corr.get("level"), fallback=4.0)
        topic = str(corr.get("id") or corr.get("name") or "macro").lower()
        for headline in _pattern_headlines(corr) or [{}]:
            title = headline.get("title") if isinstance(headline, dict) else None
            items.append(
                {
                    "title": title or f"Cross-source correlation: {corr.get('name', topic)}",
                    "summary": f"Source count={corr.get('sourceCount')} level={corr.get('level')}",
                    "source": headline.get("source") if isinstance(headline, dict) else "pattern_api",
                    "url": headline.get("link") if isinstance(headline, dict) else None,
                    "topics": [topic, str(corr.get("category", "macro")).lower()],
                    "severity": severity,
                }
            )

    for signal in payload.get("predictiveSignals", []) or []:
        if not isinstance(signal, dict):
            continue
        confidence = float(signal.get("confidence") or 0.0)
        score = float(signal.get("score") or 0.0)
        severity = max(_level_to_severity(signal.get("level"), fallback=0.0), min(10.0, confidence / 10.0))
        if score >= 45:
            severity = max(severity, 7.0)
        topic = str(signal.get("id") or signal.get("name") or "macro").lower()
        impact = signal.get("marketImpact") if isinstance(signal.get("marketImpact"), dict) else {}
        for headline in _pattern_headlines(signal) or [{}]:
            title = headline.get("title") if isinstance(headline, dict) else None
            items.append(
                {
                    "title": title or f"Predictive signal: {signal.get('name', topic)}",
                    "summary": signal.get("prediction") or f"confidence={confidence} score={score}",
                    "source": headline.get("source") if isinstance(headline, dict) else "pattern_api",
                    "url": headline.get("link") if isinstance(headline, dict) else None,
                    "topics": [
                        topic,
                        str(signal.get("category", "macro")).lower(),
                        str(impact.get("direction", "")).lower(),
                    ],
                    "severity": severity,
                }
            )

    return items


def payload_to_news_items(payload: Any) -> list[dict[str, Any]]:
    """Convert supported friend API payload shapes to normalized raw news items."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("friend API payload must be JSON object or list")
    if any(key in payload for key in ("emergingPatterns", "momentumSignals", "predictiveSignals")):
        return _flatten_pattern_payload(payload)
    for key in ("items", "news", "articles", "data"):
        if isinstance(payload.get(key), list):
            return [item for item in payload[key] if isinstance(item, dict)]
    return [payload]


def normalize_news_item(
    item: dict[str, Any],
    *,
    market_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize one headline into risk-monitor fields."""
    title = str(item.get("title") or item.get("headline") or item.get("name") or "").strip()
    summary = str(item.get("summary") or item.get("description") or item.get("body") or "").strip()
    text = " ".join(part for part in (title, summary) if part)
    severity = _infer_severity(text, item.get("severity"))
    topics = _coerce_topics(item.get("topics") or item.get("topic"), text)
    affected = _affected_strategies(topics)
    affected_assets = _affected_asset_classes(topics)
    affected_tickers = _affected_tickers(topics)
    if not affected and severity >= 7:
        severity = 6.5
    confirmations = _market_confirmations(affected_tickers, market_items)
    warning_level = _warning_level(
        severity=severity,
        affected_strategies=affected,
        affected_tickers=affected_tickers,
        market_confirmations=confirmations,
    )
    confidence = _confidence(severity, topics, affected, item.get("confidence"))
    timestamp = item.get("published_at") or item.get("timestamp") or item.get("date")
    reasoning = _reasoning(
        topics=topics,
        affected_strategies=affected,
        affected_tickers=affected_tickers,
        market_confirmations=confirmations,
        warning_level=warning_level,
    )
    return {
        "timestamp": timestamp,
        "title": title or "(untitled headline)",
        "summary": summary,
        "url": item.get("url") or item.get("link"),
        "source": item.get("source") or item.get("publisher") or "friend_api",
        "published_at": timestamp,
        "severity": severity,
        "watch_level": _watch_level(severity),
        "warning_level": warning_level,
        "keywords": _keywords(topics, text),
        "topics": topics,
        "affected_asset_class": affected_assets,
        "affected_tickers": affected_tickers,
        "affected_strategies": affected,
        "portfolio_impact": "portfolio-relevant" if affected_assets or affected_tickers else "context only",
        "strategy_impact": "strategy-linked" if affected else "none",
        "market_confirmations": confirmations,
        "reasoning": reasoning,
        "confidence": confidence,
        "requires_human_review": warning_level in {"warning", "urgent"},
    }


def build_news_risk_snapshot(
    api_url: str | None = None,
    *,
    raw_items: list[dict[str, Any]] | None = None,
    market_items: list[dict[str, Any]] | None = None,
    max_items: int = 20,
) -> dict[str, Any]:
    """Build a JSON-serializable news risk snapshot."""
    resolved_url = api_url or os.environ.get("FRIEND_NEWS_API_URL")
    if raw_items is None:
        if not resolved_url:
            return {
                "generated_at_utc": _utc_now(),
                "status": "not_configured",
                "data_mode": "news_monitor_friend_api",
                "api_url_configured": False,
                "headline_count": 0,
                "max_severity": 0.0,
                "urgent_review_count": 0,
                "watch_count": 0,
                "official_risk_decision_allowed": False,
                "note": "Set FRIEND_NEWS_API_URL or pass --news-api-url to enable news monitoring.",
                "items": [],
            }
        raw_items = payload_to_news_items(fetch_friend_payload(resolved_url))

    normalized = [normalize_news_item(item, market_items=market_items) for item in raw_items]
    normalized = sorted(
        normalized,
        key=lambda row: (-float(row["severity"]), str(row.get("published_at") or "")),
    )[:max_items]
    max_sev = max((float(row["severity"]) for row in normalized), default=0.0)
    urgent = sum(1 for row in normalized if row["watch_level"] == "urgent_review")
    watch = sum(1 for row in normalized if row["watch_level"] == "watch")
    warning_count = sum(1 for row in normalized if row["warning_level"] == "warning")
    urgent_warning_count = sum(1 for row in normalized if row["warning_level"] == "urgent")
    affected = sorted(
        {
            strategy
            for row in normalized
            for strategy in row.get("affected_strategies", [])
        }
    )
    return {
        "generated_at_utc": _utc_now(),
        "status": "success",
        "data_mode": "news_monitor_friend_api",
        "api_url_configured": bool(resolved_url),
        "headline_count": len(normalized),
        "max_severity": max_sev,
        "urgent_review_count": urgent,
        "watch_count": watch,
        "warning_count": warning_count,
        "urgent_warning_count": urgent_warning_count,
        "affected_strategies": affected,
        "official_risk_decision_allowed": False,
        "note": (
            "News severity is context for human review and strategy monitoring. "
            "It does not authorize execution."
        ),
        "items": normalized,
    }
