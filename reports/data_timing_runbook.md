# Data Timing Runbook (OpenBB Prototype)

Audience: risk manager review, intern operators, and engineering handoff.

This runbook defines how price data moves from raw vendor feeds to official end-of-day (EOD) risk metrics. It prevents calendar mismatches from being treated as portfolio strategy signals.

## Raw Feed

- **Location:** `data/raw/openbb_price_history.csv`
- **Source tag:** `openbb_yfinance`
- **Purpose:** archival vendor pull from OpenBB/yfinance; not official risk input.

Raw data may be **asynchronous** across instruments. ETFs, VIX, futures proxies, FX, and commodities can appear on different trading calendars. A date row may include VIX while equity ETFs are missing (for example holidays or partial vendor coverage).

**Operator rule:** never feed `data/raw/` directly into official portfolio risk metrics or the after-market report.

## Processed Official EOD Panel

- **Location:** `data/processed/openbb_price_history_aligned.csv`
- **Purpose:** synchronized panel where every required ticker has exactly one non-null close on each retained date.

Processing policy (`scripts/process_openbb_prices.py`):

- Keep only **complete** dates (all required tickers present).
- Drop incomplete dates.
- **No forward-fill.**
- Do not invent prices.

Run quality check before metrics:

```bash
python scripts/check_openbb_data_quality.py
```

Official EOD is usable only when processed readiness is `official_eod_ready` and validation passes.

## Live Monitor vs Official Risk Snapshot

| Layer | Timing | Label | Use |
|-------|--------|-------|-----|
| Raw feed | Vendor pull, may be partial | `openbb_yfinance` raw | Diagnostics only |
| Processed panel | Synchronized closes | aligned official EOD | `build_openbb_metrics.py` |
| Metrics snapshot | Close-of-market | `openbb_yfinance_computed_from_prices` | Rule engine dry-run |
| Future live monitor | Intraday/overnight | separate label (not implemented) | Watchlist only |

**Do not mix** GLD ETF close with gold futures overnight moves as if they share the same timestamp. They answer different questions (fund NAV proxy vs futures session).

Overnight/live moves may be monitored later for situational awareness, but must be labeled separately and must **not** overwrite close-market strategy decisions.

## Market Monitor Snapshot

- **Script:** `python scripts/build_market_monitor_snapshot.py`
- **Output:** `output/openbb_market_monitor_snapshot.json`
- **Inputs:** latest observations from `data/raw/openbb_price_history.csv`; `official_eod_date` from `data/processed/openbb_price_history_aligned.csv`

This is the right place for numbers to keep moving. Each ticker can show its latest available raw close and return even when calendars diverge. A ticker may display `newer_than_official_eod` or `stale_vs_official_eod` relative to the processed official EOD anchor.

**Governance:**

- `official_risk_decision_allowed` is always **false** in the monitor snapshot.
- Newer live or overnight observations are **watchlist context** only.
- They must **not** overwrite official EOD strategy decisions, rule-engine triggers, or after-market report escalation.
- Do not forward-fill missing monitor prices.

Dashboard Tab 1 may display this snapshot read-only when the JSON file exists. It does not replace sample replay metrics or actionable alerts.

## Overnight Watchlist

- **Script:** `python scripts/build_overnight_watchlist.py`
- **Input:** `output/openbb_market_monitor_snapshot.json`
- **Output:** `output/openbb_overnight_watchlist.json`

This is where newer-than-close observations belong. Gold, VIX, oil, and USD moves after the official EOD anchor should be reviewed as **context** for what moved overnight or before the next open. They must **not** overwrite the official EOD report, rule-engine triggers, or strategy switch logic.

If the overnight watchlist flags `urgent_review` (for example a large VIX move), the next step is **human review before next open**, not an automatic strategy switch or rebalance instruction.

`official_risk_decision_allowed` remains **false**. Official risk decisions still require the processed aligned panel and quality gate.

Future extensions may add distinct source labels (for example `overnight_monitor_*`) but must never replace the official EOD panel or the primary escalation ladder without explicit human review.

## What Not To Do

1. **Do not** let VIX-only holiday rows trigger portfolio-level strategy decisions.
2. **Do not** forward-fill missing closes for official EOD risk metrics.
3. **Do not** treat raw incomplete panels as official after-market report input.
4. **Do not** merge asynchronous asset classes into one timestamp without alignment.
5. **Do not** run `build_openbb_metrics.py` on raw CSV by default; use the processed aligned file.

If the processed panel is not `official_eod_ready`, the after-market report must **not** be treated as official.

## Daily Pipeline Runner

- **Script:** `python scripts/run_openbb_daily_pipeline.py`
- **Audit output:** `output/openbb_daily_pipeline_run.json`

Correct order inside the runner:

1. `process_openbb_prices` (aligned panel)
2. `check_openbb_data_quality` (official EOD gate)
3. `build_openbb_metrics` (official EOD snapshot + rule-engine dry-run counts)
4. `build_market_monitor_snapshot` (read-only latest obs)
5. `build_overnight_watchlist` (context-only flags)

**Governance:**

- Fetch raw prices separately when needed: `python scripts/fetch_openbb_prices.py`
- The pipeline does **not** fetch live data by default.
- If pipeline `status` is **failed**, OpenBB-based daily outputs are **not** official for that run.
- If `official_eod_usable` is **false**, stop and fix data before treating metrics as official.
- Overnight watchlist remains **context-only** and must not drive strategy switches.
- The dashboard hides OpenBB monitor/watchlist sections unless the latest pipeline report is `success` and required artifacts exist.
- Each pipeline report includes `run_id` so operators can tie displayed artifacts back to a specific run.

## Daily Operating Procedure

1. Fetch raw prices: `python scripts/fetch_openbb_prices.py`
2. Run daily pipeline: `python scripts/run_openbb_daily_pipeline.py`
3. Review `output/openbb_daily_pipeline_run.json` and `output/openbb_data_quality_report.json`
4. Review official EOD metrics (`output/openbb_metrics_snapshot.json`)
5. Review market monitor (`output/openbb_market_monitor_snapshot.json`)
6. Review overnight watchlist (`output/openbb_overnight_watchlist.json`)
7. Sample replay (`data/samples/`) remains unchanged for dashboard prototype demos.

`build_openbb_metrics.py` also runs the official EOD quality gate before writing
`output/openbb_metrics_snapshot.json`. A failed gate means no official OpenBB
metrics snapshot should be used for report or strategy review.

When quality fails, fix data or wait for the next complete session; do not patch with forward-fill.
