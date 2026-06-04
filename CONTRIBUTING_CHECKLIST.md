# Contributing Checklist

Strict rules for contributors and AI assistants working on `live_strategy`. Violations should block merge until corrected.

## Research and strategy integrity

- [ ] **No strategy recommendation without backtest evidence** - Config or docs may describe a strategy, but activation requires reproducible backtest artifacts and assumptions.
- [ ] **No live signal without data timestamp and source validation** - Every metric must carry `as_of_date`, source, and staleness checks before alerts fire.
- [ ] **No daily overfitting** - Do not rewrite strategy logic, thresholds, or weights daily to fit the latest market move.
- [ ] **No look-ahead bias** - Signals, regimes, and portfolio metrics must use only information available at the decision time.
- [ ] **No survivorship bias without disclosure** - If universes change over time, document bias and sensitivity.

## Data and secrets

- [ ] **No API keys or credentials committed** - Use `.env` (gitignored) and `secrets/` (gitignored) only locally.
- [ ] **No fake market data** - Do not label mock JSON or synthetic series as Bloomberg/OpenBB/live feeds.
- [ ] **Raw and processed data stay gitignored** - Commit policy under `data/config/` and small examples under `data/samples/` only.

## Engineering and UI

- [ ] **No dashboard metric without underlying computation in `src/`** - Dashboard layers display; they do not invent analytics.
- [ ] **No action recommendation without human review flag** - Priority >= 3 outcomes and strategy switches must surface `requires_human_review` or equivalent.
- [ ] **No trade execution commands** - Outputs are monitor, propose, flag, pause candidate, escalate; not buy/sell orders.

## Backtesting and validation

- [ ] **No fake backtest or walk-forward results** - Do not commit performance tables, Sharpe ratios, or equity curves without the code, data snapshot, and config hash that produced them.
- [ ] **Tests required when adding logic:**
  - Config validation (`tests/test_config_integrity.py`)
  - Return calculation (when implemented)
  - Risk metrics (VaR, drawdown - when implemented)
  - Backtest train/test split (when implemented)
  - Walk-forward window logic (when implemented)
  - Rule engine behavior (`tests/test_rule_engine.py`)

## Pull request minimum

- [ ] `python -m pytest tests/test_config_integrity.py tests/test_rule_engine.py -q` passes
- [ ] README or roadmap updated if scope or claims change
- [ ] No changes to internship context markdown unless explicitly requested
- [ ] Disclaimer preserved: research/education only; not investment advice; not automated trading
