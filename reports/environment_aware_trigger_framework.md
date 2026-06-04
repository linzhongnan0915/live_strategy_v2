# Environment-Aware Trigger Framework

This document is **prototype risk governance design**. It explains how trigger logic
should adapt across market environments, including escalation and de-escalation /
re-risk review. It is **not** fully implemented in code today. Current behavior
remains in `src/regime/rule_engine.py` and related configs until later phases.

---

## 1. Why Fixed Thresholds Are Not Enough

Absolute thresholds (for example VIX >= 20, portfolio VaR >= 1.0) are useful
**alarms**, but they are not sufficient for risk-manager decisions by themselves.

- **VIX 24 in a calm market** is different from **VIX 24 after falling from 45**.
  The level is the same; the **trend, persistence, and prior regime** are not.
- A one-day bounce after a crisis is not the same as **sustained stabilization**.
- **Credit stress** that is improving for ten days should not be treated like
  credit stress that is worsening for ten days, even if both days show HYG/LQD
  slightly negative.

Fixed thresholds identify **stress**. Trend, persistence, cross-asset context,
and environment state determine **escalation vs de-escalation vs re-risk review**.

This framework is **governance and design guidance**, not final calibrated logic.
All bands require historical calibration, walk-forward testing, and false-positive
audits before operational use.

---

## 2. Four Layers

The workstation should keep these layers separate:

| Layer | Purpose | Current prototype |
|-------|---------|-------------------|
| 1. Metric-level status | Where is pressure building on a single input? | `metric_status_policy.csv`, `metric_status.py` |
| 2. Rule-level confirmation | Which regime rules are **confirmed** after multi-signal logic? | `rule_engine.py`, `regime_thresholds.csv` |
| 3. Environment / state classification | What **regime-like context** are we in (including stabilization)? | `environment_states.csv` (skeleton only; not wired) |
| 4. Decision-level escalation or de-escalation review | Overall posture and human review requirements | Report executive summary, dashboard ERM counts |

Flow:

`metrics -> metric status -> rule alerts -> environment state (future) -> escalation or de-escalation review`

Layer 3 is **design-only** today. Layers 1, 2, and 4 are partially implemented.

---

## 3. Environment States

Reference rows: `data/config/environment_states.csv`.

### normal_risk_on

| Field | Guidance |
|-------|----------|
| Typical signals | VIX calm; SPY return supportive; HYG/LQD neutral to positive; low alert count |
| Required confirmation | Calm VIX plus positive equity; no active stress blockers |
| Green/yellow/red | **Green** informational monitoring; yellow only if isolated metric flicker |
| Monitor tomorrow | Benchmark drift; strategy tracking; liquidity of inputs |
| Review actions | Monitor alignment; optional risk budget release review after persistence |
| Not automatic | Risk-on tilt; strategy switch; any execution |

### volatility_stress

| Field | Guidance |
|-------|----------|
| Typical signals | VIX >= 20 or large 1d VIX change; equity may be soft but not full risk-off |
| Required confirmation | `high_volatility` per engine; red only if VIX >= 30 plus VIX spike or equity stress |
| Green/yellow/red | **Yellow** watchlist; VIX >= 30 alone stays yellow; **red** only with confirmed paired stress |
| Monitor tomorrow | VIX level and change; SPY short-horizon return; vol risk budget |
| Review actions | Flag defensive adjustment candidate; human review |
| Not automatic | Hedge execution; claiming crisis over after one calm day |

### risk_off_equity_stress

| Field | Guidance |
|-------|----------|
| Typical signals | Elevated VIX plus SPY weakness or SPY drawdown |
| Required confirmation | `risk_off` policy: VIX plus equity confirmation (not VIX alone) |
| Green/yellow/red | **Yellow** risk-off review; **red** `risk_off` only with SPY drawdown confirmation; VaR/drawdown are separate hard-limit alerts |
| Monitor tomorrow | Equity beta sleeves; defensive rotation candidates |
| Review actions | Propose defensive rotation review; reduce risk budget subject to human approval |
| Not automatic | Automatic de-risking trades |

### credit_stress

| Field | Guidance |
|-------|----------|
| Typical signals | HYG/LQD relative stress plus VIX confirmation |
| Required confirmation | Both credit and vol thresholds in `rule_engine` |
| Green/yellow/red | **Red** when confirmed; metric-only credit stress stays **yellow** watch |
| Monitor tomorrow | HY vs IG relative; spread proxies; cyclical beta |
| Review actions | Flag credit defense; propose HY reduction subject to human review |
| Not automatic | Automatic HY exit; all-clear on one-day bounce |

### liquidity_crisis

| Field | Guidance |
|-------|----------|
| Typical signals | Severe HYG/LQD dislocation plus VIX >= 28; often with VaR or drawdown breach |
| Required confirmation | `liquidity_stress` dual threshold; portfolio breaches amplify |
| Green/yellow/red | **Red** immediate human review |
| Monitor tomorrow | Front-end rates proxies; IG vs HY; portfolio liquidity metrics |
| Review actions | Propose liquidity defense; risk budget cut subject to human review |
| Not automatic | Liquidation; panic switches |

### rates_inflation_shock

| Field | Guidance |
|-------|----------|
| Typical signals | TIP strength plus USO or TLT duration selloff confirmation |
| Required confirmation | `inflation_pressure` policy; severe portfolio loss elevates |
| Green/yellow/red | **Yellow** `inflation_pressure` review; portfolio VaR/drawdown breaches are separate hard-limit reds |
| Monitor tomorrow | TIP, USO, TLT; real-rate and oil proxies |
| Review actions | Propose rates/inflation hedge review; reduce duration candidate |
| Not automatic | Duration slash based on TIP alone |

### geopolitical_event_shock

| Field | Guidance |
|-------|----------|
| Typical signals | Headline severity plus cross-asset confirmation |
| Required confirmation | Both gates; market-only moves are not enough |
| Green/yellow/red | **Red** geopolitical review when confirmed |
| Monitor tomorrow | Headline feed quality; gold, USD, rates legs |
| Review actions | Pause/switch candidate subject to backtest and human approval |
| Not automatic | Automatic geopolitical hedge execution |

### stabilization_re_risk_review

| Field | Guidance |
|-------|----------|
| Typical signals | Prior stress improving; metrics calming for N days; no new hard breaches |
| Required confirmation | Persistence window (not implemented); human sign-off |
| Green/yellow/red | **Review band** - not automatic return to risk-on |
| Monitor tomorrow | Whether improvement persists; false recovery risk |
| Review actions | Propose risk budget release review; reduce defensive posture subject to human approval |
| Not automatic | Automatic re-risking; treating one-day rally as all-clear |

---

## 4. Escalation vs De-Escalation

### Escalation

Risk is **getting worse**, not merely elevated.

Triggers include:

- Hard breaches (VaR ratio >= 1.0, drawdown limit, liquidity dual confirmation)
- Multi-signal stress confirmation (credit plus vol, geopolitical gates)
- Rising alert count and worsening metric status (more red, fewer green)

Outcome: higher rule escalation (yellow/red), more human review, defensive proposals.

### De-Escalation

Risk is **stabilizing** after a stress episode.

Indicators include:

- Stress metrics improving (VIX falling, HYG/LQD relative stabilizing)
- Fewer yellow/red rule alerts
- VaR ratio and drawdown moving back inside watch bands

Outcome: move toward `stabilization_re_risk_review` - **monitor stabilization**,
not automatic green posture.

### Re-Risk Review

Defensive posture may be **reviewed**, not automatically reduced.

Language to use:

- propose risk budget release review
- reduce defensive posture subject to human approval
- monitor stabilization

Language **not** to use:

- buy
- sell
- execute
- trade now

Re-risk requires **persistence** (N-day rule) and human approval. It is not the
mirror image of a one-day red alert.

---

## 5. Decision Matrices

### High Volatility

| Condition | Typical posture |
|-----------|-----------------|
| VIX < 20 | Green / no high_volatility alert |
| VIX 20-30 | Yellow unless other stress confirms red |
| VIX >= 30 alone | Yellow `high_volatility` (not red) |
| VIX >= 30 + VIX spike or equity stress | Red `high_volatility` (confirmed_regime_red) |
| VIX falling from crisis peak | Stabilization watch - not immediate green |

### Risk-Off

| Condition | Typical posture |
|-----------|-----------------|
| VIX only | No risk_off alert |
| Equity weakness only | Metric watch |
| VIX + SPY weakness | Yellow risk_off |
| VIX + SPY drawdown (linked threshold) | Red `risk_off` |
| Portfolio VaR or drawdown limit breach | Red `var_breach` / `drawdown_breach` (hard_limit_red; separate from risk_off) |

### Credit Stress

| Condition | Typical posture |
|-----------|-----------------|
| HYG/LQD stress only | Yellow metric watch |
| VIX only | Volatility watch |
| HYG/LQD stress + VIX confirmation | Red credit review |
| HYG/LQD stabilizes N days + VIX falling | De-escalation review |

### Liquidity Crisis

| Condition | Typical posture |
|-----------|-----------------|
| Severe HYG/LQD + VIX >= 28 | Red |
| VaR/drawdown breach with credit stress | Red |
| One-day bounce | Not de-escalation - require persistence |

### Rates / Inflation

| Condition | Typical posture |
|-----------|-----------------|
| TIP only | Metric watch - no inflation rule |
| TIP + oil or duration selloff | Yellow inflation/rates review |
| TIP + oil or duration confirmation | Yellow `inflation_pressure` (rule stays yellow/red per engine; not hard-limit red by itself) |
| Portfolio VaR or drawdown limit breach | Red hard-limit alerts (co-primary with regime context) |
| TLT stops falling, oil stabilizes, VaR improves | De-escalation review |

### Geopolitical

| Condition | Typical posture |
|-----------|-----------------|
| Headline only | News watch |
| Market moves only | Market stress watch |
| Headline severity + cross-asset confirmation | Red geopolitical review |
| Headline decline + cross-asset normalization | De-escalation review |

### VaR / Drawdown

| Condition | Typical posture |
|-----------|-----------------|
| Watch band | Yellow |
| Breach | Red |
| VaR/drawdown stabilizing N days | De-escalation review |

---

## 6. Regime-Aware Alert Hierarchy

**Current runtime (Step 20):** `src/regime/rule_engine.py` uses static
`ALERT_SUBSUME_BY` only (`liquidity_stress` subsumes `credit_stress` when both fire).
This is presentation metadata; audit tables keep all alerts.

**Planned config (Step 20A):** `data/config/alert_hierarchy.csv` defines
regime-dependent dominant/subsumed pairs keyed by `environment_state` (aligned with
`environment_states.csv`). The file is **validated** in `config_loader` but
**not wired** to runtime yet.

| Column | Role |
|--------|------|
| `environment_state` | Environment id (e.g. `liquidity_crisis`, `credit_stress`) |
| `dominant_rule_id` | Primary escalation rule for UX and review focus |
| `subsumed_rule_id` | Lower-level or supporting rule shown as context |
| `priority_rank` | Order when multiple subsumed rules apply (1 = highest) |
| `relationship_type` | `dominates` or `context_only` |
| `rationale` | Risk-manager explanation text |
| `dashboard_label` | Short label for future dashboard grouping |
| `active_by_default` | Whether row is active when config is wired (TRUE/FALSE) |

### Governance rules

1. **Hard limits are never subsumed:** `var_breach` and `drawdown_breach` may remain
   co-primary with regime alerts because portfolio limit breaches require direct review.
2. **Evidence is not deleted:** subsumed rules stay in `alerts` and `all_alerts` audit tables.
3. **Environment required:** hierarchy rows apply only when the classified environment matches.
4. **Not runtime yet:** config is validated in `load_alert_hierarchy()`; runtime hierarchy
   remains static `ALERT_SUBSUME_BY` until environment classification and config wiring land.

### Example rows (prototype)

| environment_state | dominant | subsumed |
|-------------------|----------|----------|
| `liquidity_crisis` | `liquidity_stress` | `credit_stress`, `high_volatility` |
| `credit_stress` | `credit_stress` | `high_volatility` |
| `geopolitical_event_shock` | `geopolitical_shock` | `oil_shock`, `usd_pressure`, `high_volatility` |
| `rates_inflation_shock` | `inflation_pressure` | `rates_up`, `oil_shock` |
| `risk_off_equity_stress` | `risk_off` | `high_volatility` (not drawdown/VaR limits) |

---

## 7. Current Implementation Gaps

| Gap | Impact |
|-----|--------|
| Informational green rules during red stress | `risk_on`, `low_volatility`, `credit_calm` may still appear beside red alerts; should be suppressed or visually separated |
| Metric status missing rates/inflation bands | No TIP, USO, TLT rows in `metric_status_policy.csv` |
| No de-escalation / re-risk rules | `stabilization_re_risk_review` is documentation only |
| No environment state wiring | `environment_states.csv` not used by `rule_engine` |
| Regime hierarchy config not runtime | `alert_hierarchy.csv` validated only; static `ALERT_SUBSUME_BY` still active |
| No persistence logic | No N-day clear or N-day improving windows |
| Thresholds not historically calibrated | Prototype values only |
| No false-positive / false-negative audit | Regime-level trigger quality unknown |
| No trend context | VIX 24 after 45 vs stable 24 treated the same at metric layer |

---

## 8. Proposed Next Implementation Steps

Priority order:

1. **Suppress green informational alerts** when yellow/red alerts are active
   (or separate them in dashboard/report as "informational only").
2. **Add metric status bands** for TIP return, USO return, TLT return.
3. **Add de-escalation / re-risk review rules** as a separate proposal layer
   (not mixed with stress fire rules).
4. **Add persistence windows**: N-day clear, N-day improving before de-escalation.
5. **Backtest trigger false-positive behavior** by regime (walk-forward, stress windows).

Do not implement steps 3-5 without governance review and historical evidence.

---

## Related Artifacts

- [trigger_logic_user_guide.md](trigger_logic_user_guide.md) - current three-layer user guide
- `data/config/environment_states.csv` - environment skeleton (not wired)
- `data/config/alert_hierarchy.csv` - regime-aware dominance config (not wired)
- `src/regime/rule_engine.py` - current confirmation and escalation logic
