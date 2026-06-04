"""Tests for overnight watchlist (no network)."""

import json
from pathlib import Path

import pytest

from src.monitoring.overnight_watchlist import build_overnight_watchlist

ROOT = Path(__file__).resolve().parents[1]


def _write_monitor(tmp_path: Path, items: list[dict], official_eod_date: str = "2026-04-14") -> Path:
    path = tmp_path / "monitor.json"
    payload = {
        "official_eod_date": official_eod_date,
        "official_risk_decision_allowed": False,
        "items": items,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _base_item(**overrides) -> dict:
    row = {
        "ticker": "SPY",
        "asset_class": "Equity",
        "risk_bucket": "core_equity",
        "target_weight": 0.18,
        "latest_date": "2026-04-14",
        "official_eod_date": "2026-04-14",
        "latest_close": 500.0,
        "latest_return_pct": 0.5,
        "timing_status": "official_eod_aligned",
        "is_stale": False,
    }
    row.update(overrides)
    return row


def test_newer_than_official_eod_included(tmp_path):
    item = _base_item(timing_status="newer_than_official_eod", latest_date="2026-04-15")
    path = _write_monitor(tmp_path, [item])
    wl = build_overnight_watchlist(path)
    assert len(wl["items"]) == 1
    assert wl["items"][0]["watch_reason"] == "newer_than_official_eod"
    assert wl["items"][0]["watch_level"] == "watch"


def test_stale_item_included(tmp_path):
    item = _base_item(is_stale=True, timing_status="stale_vs_official_eod", latest_date="2026-04-10")
    path = _write_monitor(tmp_path, [item])
    wl = build_overnight_watchlist(path)
    assert wl["items"][0]["watch_reason"] == "stale_data"
    assert wl["items"][0]["watch_level"] == "watch"


def test_large_move_included(tmp_path):
    item = _base_item(latest_return_pct=3.5)
    path = _write_monitor(tmp_path, [item])
    wl = build_overnight_watchlist(path, large_move_threshold_pct=2.0)
    assert "large_move" in wl["items"][0]["watch_reason"]
    assert wl["items"][0]["watch_level"] == "watch"


def test_vix_large_move_urgent_review(tmp_path):
    item = _base_item(
        ticker="VIX",
        asset_class="monitor_only",
        risk_bucket="monitor_only",
        target_weight=0.0,
        latest_return_pct=6.0,
    )
    path = _write_monitor(tmp_path, [item])
    wl = build_overnight_watchlist(path, vix_large_move_threshold_pct=5.0)
    assert wl["items"][0]["watch_level"] == "urgent_review"
    assert "large_move" in wl["items"][0]["watch_reason"]


def test_no_reasons_empty_watchlist(tmp_path):
    item = _base_item(latest_return_pct=0.1)
    path = _write_monitor(tmp_path, [item])
    wl = build_overnight_watchlist(path, large_move_threshold_pct=2.0)
    assert wl["items"] == []
    assert wl["summary"]["watchlist_count"] == 0


def test_official_risk_decision_allowed_false(tmp_path):
    item = _base_item(timing_status="newer_than_official_eod", latest_date="2026-04-15")
    path = _write_monitor(tmp_path, [item])
    wl = build_overnight_watchlist(path)
    assert wl["official_risk_decision_allowed"] is False
    assert wl["items"][0]["official_action_allowed"] is False


def test_missing_monitor_snapshot_fails(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_market_monitor_snapshot"):
        build_overnight_watchlist(tmp_path / "missing.json")


def test_multiple_reasons_combine(tmp_path):
    item = _base_item(
        timing_status="newer_than_official_eod",
        latest_date="2026-04-15",
        is_stale=True,
        latest_return_pct=-4.0,
    )
    path = _write_monitor(tmp_path, [item])
    wl = build_overnight_watchlist(path, large_move_threshold_pct=2.0)
    reason = wl["items"][0]["watch_reason"]
    assert "newer_than_official_eod" in reason
    assert "stale_data" in reason
    assert "large_move" in reason
    assert reason.count(";") == 2


def test_build_script_writes_json(tmp_path):
    from scripts.build_overnight_watchlist import main

    monitor = _write_monitor(
        tmp_path,
        [_base_item(timing_status="newer_than_official_eod", latest_date="2026-04-15")],
    )
    out = tmp_path / "watchlist.json"
    wl = main(monitor_path=monitor, output_path=out)
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["summary"]["watchlist_count"] == wl["summary"]["watchlist_count"]


def test_rejects_monitor_snapshot_marked_official_decision_allowed(tmp_path):
    path = tmp_path / "monitor.json"
    payload = {
        "official_eod_date": "2026-04-14",
        "official_risk_decision_allowed": True,
        "items": [_base_item(latest_return_pct=3.0)],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="monitor-only"):
        build_overnight_watchlist(path)


def test_rejects_non_numeric_latest_return_pct(tmp_path):
    item = _base_item(latest_return_pct="bad")
    path = _write_monitor(tmp_path, [item])

    with pytest.raises(ValueError, match="latest_return_pct"):
        build_overnight_watchlist(path)


def test_watchlist_sorted_by_urgency_then_move_size(tmp_path):
    items = [
        _base_item(ticker="SPY", latest_return_pct=4.0),
        _base_item(ticker="QQQ", latest_return_pct=3.0),
        _base_item(
            ticker="VIX",
            asset_class="monitor_only",
            risk_bucket="monitor_only",
            target_weight=0.0,
            latest_return_pct=6.0,
        ),
    ]
    path = _write_monitor(tmp_path, items)
    wl = build_overnight_watchlist(path, large_move_threshold_pct=2.0)

    assert [row["ticker"] for row in wl["items"]] == ["VIX", "SPY", "QQQ"]
    assert wl["items"][0]["watch_level"] == "urgent_review"
