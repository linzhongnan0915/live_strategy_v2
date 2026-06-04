# Project Roadmap

Implementation phases for the live strategy risk workstation prototype. Each phase lists objective, deliverables, completion evidence, and what must not be faked.

---

## Phase 0: Project governance and configuration

**Objective:** Establish repository structure, policy CSVs, and internship context without implementing trading or live feeds.

**Deliverables:**

- Folder layout (`data/`, `src/`, `tests/`, `scripts/`)
- `holdings.csv`, `strategy_library.csv`, `regime_rules.csv`
- Context markdown (00-05) and README

**Completion evidence:**

- Config files exist, validate manually, and are referenced in README
- No execution code paths

**Must not be faked:**

- Claiming live connectivity or performance results

---

## Phase 1: Config loader and validation

**Objective:** Centralize CSV loading with strict validation and pytest coverage.

**Deliverables:**

- `src/data/config_loader.py`
- `tests/test_config_integrity.py`
- `requirements.txt`, `pytest.ini`

**Completion evidence:**

- `load_all_configs()` passes; pytest config tests green
- Invalid configs raise `ValueError`

**Must not be faked:**

- Silent pass on bad weights, unknown strategy IDs, or invalid operators

---

## Phase 2: Prototype rule engine dry-run

**Objective:** Evaluate sample daily metrics against numeric thresholds and emit human-reviewed alert proposals.

**Deliverables:**

- `data/config/regime_thresholds.csv`
- `data/samples/mock_daily_metrics.json`
- `src/regime/rule_engine.py`
- `tests/test_rule_engine.py`
- `scripts/run_rule_engine_demo.py`

**Completion evidence:**

- Demo script runs; pytest rule engine tests green
- `missing_metrics` reported when inputs absent
- ERM green/yellow/red escalation on each alert (`escalation_level` from priority 1-2 / 3 / 4-5)

**Must not be faked:**

- Live market data presented as real; trade execution outputs

---

## Phase 3: Market data prototype and validation

**Objective:** Ingest prototype prices or returns with timestamps and source tags; validate completeness and staleness.

**Deliverables:**

- Raw ingest to `data/raw/` (gitignored)
- Processed panel in `data/processed/`
- Data quality checks (missing bars, timezone, corporate actions notes)

**Completion evidence:**

- Documented data lineage per field
- Tests for loader and date alignment

**Must not be faked:**

- Backfilled data without disclosure; future timestamps

---

## Phase 4: Portfolio PnL and risk metrics

**Objective:** Compute portfolio returns, drawdown, and VaR from holdings weights and price history.

**Deliverables:**

- `src/portfolio/` metrics builder
- JSON metrics export compatible with rule engine

**Completion evidence:**

- Unit tests: weights sum, return math, drawdown on known series
- Reproducible metrics file for a fixed date

**Must not be faked:**

- PnL without price inputs; VaR without defined methodology

---

## Phase 5: Factor exposure and risk attribution

**Objective:** Estimate factor exposures and risk contributions using observable ETF factors.

**Deliverables:**

- `src/factors/` rolling regression or exposure module
- Factor report schema for dashboard/reporting

**Completion evidence:**

- Tests for beta estimation window and no look-ahead in joins
- Documented overlap handling (e.g. SPY vs sector ETFs)

**Must not be faked:**

- Factor attributions without estimation window or multicollinearity note

---

## Phase 6: Rule-based macro regime classifier refinement

**Objective:** Refine regime rules with calibrated thresholds, AND/OR logic, and conflict resolution.

**Deliverables:**

- Updated thresholds from research
- `src/regime/` classifier and rule priority resolver

**Completion evidence:**

- Historical label audit on past crises (documented, not auto-traded)
- Tests for threshold edge cases and multi-rule fires

**Must not be faked:**

- Perfect regime labels without out-of-sample evaluation

---

## Phase 7: Strategy backtest engine

**Objective:** Backtest each library strategy with costs, slippage, and risk controls per blueprint.

**Deliverables:**

- `src/strategy/` backtest runner (e.g. QLIB integration per notes)
- Per-strategy backtest report artifacts in `output/` (gitignored)

**Completion evidence:**

- Reproducible run config and saved metrics (Sharpe, max DD, turnover)
- Tests: no look-ahead in signals, rebalance timing

**Must not be faked:**

- Backtest results without code path, data, and assumptions file

---

## Phase 8: Walk-forward evaluation

**Objective:** Rolling or walk-forward optimization with out-of-sample reporting.

**Deliverables:**

- WFO runner and summary tables
- Comparison in-sample vs out-of-sample

**Completion evidence:**

- Documented train/test windows; pytest on split logic
- Failure mode analysis for overfitting

**Must not be faked:**

- Walk-forward charts without stored window definitions

---

## Phase 9: News/event risk layer

**Objective:** Ingest headlines, severity scoring, and cross-asset confirmation for geopolitical rules.

**Deliverables:**

- `src/news/` ingest and classify stubs
- Event log linked to `geopolitical_shock` rules

**Completion evidence:**

- Timestamped headline records; precision/recall notes on sample set
- Tests for false positive handling

**Must not be faked:**

- Synthetic news passed off as vendor feeds

---

## Phase 10: Dashboard prototype

**Objective:** Read-only Streamlit (or similar) views for market, risk, and strategy screens.

**Deliverables:**

- `dashboard/` pages calling `src/` only
- Display of rule engine alerts and config metadata

**Completion evidence:**

- Screenshot or runbook; no embedded research logic in UI files
- Each metric traceable to `src/` computation

**Must not be faked:**

- Hard-coded dashboard KPIs without underlying series

---

## Phase 11: After-market report generator

**Objective:** Generate daily PDF/Markdown risk memo: performance, regimes, alerts, proposals, watchlist.

**Deliverables:**

- `src/reporting/` template and export to `reports/` or `output/`

**Completion evidence:**

- Sample report for a fixed date using real computed inputs
- Human review section always present

**Must not be faked:**

- Narrative claims not supported by same-day metrics and config version hash
