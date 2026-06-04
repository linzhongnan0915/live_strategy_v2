"""Tests for friend/API news risk monitor."""

from src.news.news_monitor import build_news_risk_snapshot, normalize_news_item, payload_to_news_items


def test_critical_news_maps_to_urgent_review_and_strategies():
    item = normalize_news_item(
        {
            "title": "Breaking oil attack raises geopolitical risk",
            "summary": "Energy markets react to missile attack.",
            "topics": ["oil", "geopolitical"],
            "severity": 9,
        }
    )

    assert item["severity"] == 9
    assert item["watch_level"] == "urgent_review"
    assert item["warning_level"] == "watch"
    assert item["requires_human_review"] is False
    assert "energy_inflation_shock_rotation" in item["affected_strategies"]
    assert "gold_geopolitical_hedge_sleeve" in item["affected_strategies"]
    assert "USO" in item["affected_tickers"]


def test_keyword_severity_inference_without_provided_score():
    item = normalize_news_item(
        {
            "headline": "Urgent credit downgrade creates liquidity pressure",
            "description": "Credit and liquidity conditions deteriorate.",
        }
    )

    assert item["severity"] >= 7
    assert "credit" in item["topics"]
    assert "liquidity" in item["topics"]
    assert "credit_stress_defensive_overlay" in item["affected_strategies"]
    assert item["warning_level"] == "watch"


def test_news_snapshot_not_configured_when_no_url_or_items():
    snap = build_news_risk_snapshot(api_url=None, raw_items=None)

    assert snap["status"] == "not_configured"
    assert snap["headline_count"] == 0
    assert snap["official_risk_decision_allowed"] is False


def test_news_snapshot_summarizes_urgent_counts():
    snap = build_news_risk_snapshot(
        raw_items=[
            {"title": "Breaking war and oil shock", "severity": 8.5},
            {"title": "Technology earnings update", "severity": 3.0},
        ]
    )

    assert snap["status"] == "success"
    assert snap["headline_count"] == 2
    assert snap["max_severity"] == 8.5
    assert snap["urgent_review_count"] == 1
    assert snap["urgent_warning_count"] == 0
    assert snap["official_risk_decision_allowed"] is False


def test_pattern_payload_maps_to_news_items():
    payload = {
        "ok": True,
        "summary": {"predictiveSignalsCount": 1},
        "emergingPatterns": [
            {
                "id": "fed-rates",
                "name": "Fed Rates",
                "category": "Economy",
                "count": 8,
                "level": "high",
                "headlines": [{"title": "Fed rate risk rises", "source": "Reuters"}],
            }
        ],
        "momentumSignals": [
            {
                "id": "inflation",
                "name": "Inflation",
                "category": "Economy",
                "current": 6,
                "delta": 4,
                "momentum": "surging",
                "headlines": [{"title": "Inflation momentum surges", "source": "CNBC"}],
            }
        ],
        "predictiveSignals": [
            {
                "id": "credit-stress",
                "name": "Credit Stress",
                "category": "Finance",
                "score": 45,
                "confidence": 75,
                "level": "high",
                "prediction": "Credit signal bearish within 4h",
                "marketImpact": {"direction": "bearish"},
                "headlines": [{"title": "Credit spreads widen", "source": "Bloomberg"}],
            }
        ],
    }

    items = payload_to_news_items(payload)
    snap = build_news_risk_snapshot(raw_items=items)

    assert len(items) == 3
    assert snap["headline_count"] == 3
    assert snap["max_severity"] >= 8
    assert snap["urgent_review_count"] >= 1
    assert "credit_stress_defensive_overlay" in snap["affected_strategies"]


def test_non_market_relevant_high_news_is_capped_to_watch():
    item = normalize_news_item(
        {
            "title": "Local election coverage expands across multiple outlets",
            "topics": ["election", "politics"],
            "severity": 8,
        }
    )

    assert item["severity"] == 6.5
    assert item["watch_level"] == "watch"
    assert item["warning_level"] == "watch"
    assert item["affected_strategies"] == []
    assert item["requires_human_review"] is False


def test_market_relevant_pattern_keeps_urgent_review():
    item = normalize_news_item(
        {
            "title": "Credit stress and bank crisis hits markets",
            "topics": ["credit-stress", "bank-crisis"],
            "severity": 8,
        }
    )

    assert item["watch_level"] == "urgent_review"
    assert "credit_stress_defensive_overlay" in item["affected_strategies"]


def test_bitcoin_only_news_without_crypto_exposure_does_not_trigger_urgent():
    item = normalize_news_item(
        {
            "title": "Bitcoin drops as crypto ETF flows weaken",
            "summary": "Crypto markets remain choppy.",
            "severity": 8.5,
        }
    )

    assert "crypto" in item["topics"]
    assert item["affected_tickers"] == []
    assert item["affected_strategies"] == []
    assert item["warning_level"] == "watch"
    assert item["requires_human_review"] is False
    assert "Crypto-specific" in item["reasoning"]


def test_warren_headline_does_not_false_match_war_topic():
    item = normalize_news_item(
        {
            "title": "Elizabeth Warren urges Labor Department to review crypto retirement rules",
            "summary": "Crypto policy headline.",
            "severity": 6.7,
        }
    )

    assert "war" not in item["topics"]
    assert "energy_inflation_shock_rotation" not in item["affected_strategies"]
    assert item["warning_level"] == "watch"


def test_oil_inflation_news_maps_to_energy_strategy():
    item = normalize_news_item(
        {
            "title": "Oil inflation shock lifts energy prices",
            "summary": "Crude and breakeven pressure rise.",
            "severity": 6.2,
        }
    )

    assert {"oil", "inflation"}.issubset(set(item["topics"]))
    assert "energy_inflation_shock_rotation" in item["affected_strategies"]
    assert "XLE" in item["affected_tickers"]
    assert item["portfolio_impact"] == "portfolio-relevant"


def test_fed_rates_news_maps_to_duration_strategies():
    item = normalize_news_item(
        {
            "title": "Fed rate hike risk pushes Treasury yields higher",
            "severity": 6.0,
        }
    )

    assert "fed-rates" in item["topics"] or "rates" in item["topics"]
    assert "real_rates_duration_sleeve" in item["affected_strategies"]
    assert "TLT" in item["affected_tickers"]


def test_high_severity_without_mapping_stays_watch_context_only():
    item = normalize_news_item(
        {
            "title": "Celebrity media controversy dominates social platforms",
            "severity": 9.0,
        }
    )

    assert item["severity"] == 6.5
    assert item["affected_tickers"] == []
    assert item["affected_strategies"] == []
    assert item["portfolio_impact"] == "context only"
    assert item["warning_level"] == "watch"
    assert item["requires_human_review"] is False


def test_relevant_news_with_market_confirmation_becomes_warning_or_urgent():
    item = normalize_news_item(
        {
            "title": "Oil inflation shock hits energy markets",
            "topics": ["oil", "inflation"],
            "severity": 8.4,
        },
        market_items=[
            {"ticker": "USO", "latest_return_pct": 2.1, "latest_close": 140.0},
            {"ticker": "XLE", "latest_return_pct": 1.2, "latest_close": 58.0},
        ],
    )

    assert item["warning_level"] == "urgent"
    assert item["requires_human_review"] is True
    assert len(item["market_confirmations"]) >= 1
