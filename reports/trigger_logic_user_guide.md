# Trigger Logic and Escalation User Guide

This guide explains how the Live Strategy Risk Workstation interprets prototype
sample-replay metrics. Thresholds and status bands are **not final** and must be
validated with historical data, walk-forward tests, and stress windows before any
operational use.

---

## 1. Three-Layer Logic

The system separates three layers on purpose:

1. **Metric-level status (Layer 1)**  
   Individual metrics are colored green, yellow, or red using
   `data/config/metric_status_policy.csv`. This shows **where** pressure is building.

2. **Rule-level alert (Layer 2)**  
   Confirmed risk rules (for example `high_volatility`, `credit_stress`, `risk_off`)
   fire only after linked thresholds and, for key rules, **multi-signal confirmation**
   in `src/regime/rule_engine.py`.

3. **Decision-level escalation (Layer 3)**  
   Overall green/yellow/red posture comes from the **highest confirmed rule alert**
   escalation. Red/yellow rule alerts require human review. This is not automatic
   execution.

Flow:

`metrics -> metric status -> rule alert -> final escalation`

A metric turning yellow or red does **not** mean strategy switch. A red rule alert
means **human review is required**, not trade execution.

---

## 2. Metric-Level Colors

| Color | Meaning |
|-------|---------|
| green | Within prototype normal band for that metric |
| yellow | Attention / watchlist on this metric |
| red | Severe individual metric pressure on this metric |

Metric color is a **diagnostic band**. It does not equal:

- a confirmed regime rule by itself
- final portfolio escalation by itself
- permission to switch strategy

Prototype examples (see `metric_status_policy.csv`):

- VIX level yellow at 20+, red at 30+
- SPY return yellow at -2% or worse, red at -5% or worse
- portfolio VaR yellow at 0.85+, red at 1.0+

### Missing Data Is Not Green

| Status | Meaning |
|--------|---------|
| missing | Metric expected by policy but absent or empty in the snapshot |

Missing metrics are **data-quality warnings**. They are not normal conditions and
are **not** counted in green metric totals. Review `missing_metrics` in the
dashboard metric board and `rule_engine` `missing_metrics` warnings before relying
on the report or escalation posture. Final escalation must not be interpreted as
all-clear when key inputs are missing.

---

## 3. Rule-Level Confirmation

Single metric stress often does not fire a rule. Confirmation reduces false alarms.

### Actionable vs Informational Rule Alerts

| Output bucket | escalation_level | Used for |
|---------------|------------------|----------|
| Actionable (`alerts`) | yellow, red | Main dashboard alerts, human review, overall escalation |
| Informational (`informational_alerts`) | green | Optional context only (e.g. `risk_on`, `low_volatility`, `credit_calm`) |
| Full audit (`all_alerts`) | green, yellow, red | Complete rule-engine table before separation |

Green informational rules are **not** mixed into the main actionable alert list during active stress. They do not drive escalation and do not count toward human-review-required. The after-market report and dashboard show them under **Informational context** when present, with explicit language that they are not action triggers.

### When green context appears during stress

| informational_context_mode | Actionable posture | How to read green context |
|----------------------------|-------------------|---------------------------|
| `normal_context` | No yellow/red alerts | Supportive benign context only; standard monitoring |
| `caution_context` | Yellow actionable, no red | Local benign evidence may exist; still heightened review |
| `stress_context` | Red actionable present | Benign context present but **overridden** by actionable stress |

Green context means **local benign evidence** in the rule engine (for example calm credit or positive SPY momentum on one sleeve). It is **not** permission to increase risk, reduce hedges, or treat the book as de-risked when red/yellow actionable alerts are confirmed.

The dashboard and after-market report use warning-style language in `stress_context` so green lines are not read as success signals. Green informational output never changes overall escalation or human-review counts.

### High Volatility

| Condition | Metric status (typical) | Rule alert |
|-----------|-------------------------|------------|
| VIX < 20 and no large 1d spike | green | none |
| VIX >= 20 or VIX change >= 3 | yellow on vol metrics | yellow `high_volatility` |
| VIX >= 30 alone | red metric band possible | yellow `high_volatility` (not confirmed red) |
| VIX >= 30 **and** (1d VIX spike >= 3 or SPY return <= -2% or SPY drawdown <= -5%) | vol + equity stress | red `high_volatility` (`confirmed_regime_red`) |

VIX at 22 alone does **not** produce red `high_volatility` under calibrated policy.
VIX at 30 alone does **not** produce red `high_volatility`; extreme VIX is yellow watch until cross-signal confirmation.

`low_volatility` is suppressed if any elevated-VIX or VIX-spike threshold fires
elsewhere in the snapshot (conflict suppression via `blocked_any`).

### Risk-On

| Condition | Rule alert |
|-----------|------------|
| SPY return >= 0 only, VIX elevated | **no** `risk_on` |
| SPY positive **and** VIX <= 18, no stress blockers | green `risk_on` |

`risk_on` requires **both** calm VIX and positive SPY momentum. Elevated VIX,
VIX spike, risk-off VIX, or credit stress thresholds block `risk_on`.

### Risk-Off

| Condition | Metric status | Rule alert |
|-----------|---------------|------------|
| VIX elevated only | yellow/red on VIX | **no** `risk_off` |
| equity weakness only | yellow/red on SPY | monitor equity; no `risk_off` without VIX gate |
| VIX >= 22 **and** SPY return <= -2% | yellow metrics | yellow `risk_off` |
| VIX >= 22 **and** SPY drawdown <= -5% | red/yellow metrics | red `risk_off` (`confirmed_regime_red` via `spy_drawdown_60d`) |

Portfolio VaR limit or portfolio drawdown limit breaches do **not** upgrade `risk_off` to red; they produce separate `var_breach` / `drawdown_breach` hard-limit reds.

### Credit Stress

| Condition | Metric status | Rule alert |
|-----------|---------------|------------|
| HYG/LQD stress only | yellow/red on credit metric | **no** confirmed `credit_stress` |
| VIX elevated only | yellow on VIX | not credit stress by itself |
| HYG/LQD stress **and** VIX >= 20 confirmation | red/yellow credit + vol | red `credit_stress` |

### Credit Calm

| Condition | Rule alert |
|-----------|------------|
| calm HYG/LQD only | metric may be green; **no** `credit_calm` if VIX elevated |
| calm HYG/LQD **and** no elevated VIX or credit stress blockers | green `credit_calm` |

### Liquidity Stress

| Condition | Rule alert |
|-----------|------------|
| severe HYG/LQD dislocation (policy threshold) **and** VIX >= 28 | red `liquidity_stress` |

### Geopolitical Shock

| Condition | Rule alert |
|-----------|------------|
| market moves only (GLD, UUP, etc.) | none |
| headline severity elevated only | news watch; no `geopolitical_shock` |
| headline severity >= 7 **and** cross-asset confirmation >= 3 | red `geopolitical_shock` |

### Inflation Pressure

| Condition | Rule alert |
|-----------|------------|
| TIP strength only | metric watch; **no** `inflation_pressure` |
| TIP strength **and** (USO >= 3% or TLT <= -2.5% over lookback) | yellow `inflation_pressure` |

### VaR

| portfolio VaR ratio | Metric status | Rule escalation |
|---------------------|---------------|-----------------|
| < 0.85 | green | none |
| 0.85 <= VaR < 1.0 | yellow | yellow watch (`portfolio_var_ratio_watch`) |
| >= 1.0 | red | red breach (`portfolio_var_ratio`) |

### Drawdown

| portfolio drawdown | Metric status | Rule escalation |
|--------------------|---------------|-----------------|
| above -5% | green | none |
| -8% < drawdown <= -5% | yellow | yellow warning |
| <= -8% | red | red limit breach |

---

## 4. Red Trigger Taxonomy and Rule Audit

Prototype escalation classes used in `src/regime/rule_engine.py`:

| Taxonomy class | Meaning | Examples in this repo |
|----------------|---------|------------------------|
| `hard_limit_red` | Single portfolio limit breach may map directly to red | `var_breach` at `portfolio_var_ratio`; `drawdown_breach` at `portfolio_drawdown_limit` |
| `extreme_market_red` | Single extreme market stress to red only when explicitly documented | None active by default; VIX >= 30 alone is **not** extreme_market_red for `high_volatility` |
| `confirmed_regime_red` | Red requires multi-threshold confirmation (rule policy + escalation logic) | `credit_stress`, `liquidity_stress`, `geopolitical_shock`, confirmed `high_volatility`, red `risk_off` |
| `yellow_watch` | Single non-limit stress signal; attention without red | `high_volatility` at VIX >= 20; `risk_off` with VIX + weak SPY return; `var_breach` watch band |

### Rule-by-rule red path audit

| rule_id | Fires when (confirmation) | Red path | Taxonomy |
|---------|---------------------------|----------|----------|
| `high_volatility` | Linked vol thresholds hit | Red only if `vix_high_min` **and** (`vix_change_1d_elevated` or `risk_off_spy_return_max` or `spy_drawdown_60d` anywhere in snapshot) | `confirmed_regime_red` |
| `risk_off` | `risk_off_vix_min` + (`risk_off_spy_return_max` or `spy_drawdown_60d`) | Red if `spy_drawdown_60d` in rule-linked hits | `confirmed_regime_red` |
| `credit_stress` | `hyg_lqd_rel_20d_stress` + `credit_stress_vix_min` | Red when rule fires | `confirmed_regime_red` |
| `liquidity_stress` | `liquidity_hyg_lqd_stress` + `vix_stress_liquidity` | Red when rule fires | `confirmed_regime_red` |
| `geopolitical_shock` | `headline_severity_min` + `cross_asset_confirm_min` | Red when rule fires | `confirmed_regime_red` |
| `var_breach` | `portfolio_var_ratio` or watch band | Red on `portfolio_var_ratio` only | `hard_limit_red` |
| `drawdown_breach` | drawdown warning or limit | Red on `portfolio_drawdown_limit` only | `hard_limit_red` |

### Alert hierarchy and subsumed context (presentation)

When multiple confirmed rules fire together, the engine may mark a **lower-level** alert as
**subsumed** for risk-manager UX. This is **governance/presentation metadata**, not deletion
of evidence.

| Field | Meaning |
|-------|---------|
| `alerts` | Full actionable yellow/red table with `is_subsumed`, `subsumed_by`, `display_group` |
| `primary_alerts` | Actionable alerts where `is_subsumed == False` (drive escalation and human review) |
| `subsumed_alerts` | Actionable alerts shown as context (e.g. `credit_stress` when `liquidity_stress` is active) |
| `all_alerts` | Full audit table before yellow/green split; always retains every fired rule |

Initial rule: active `liquidity_stress` subsumes `credit_stress`. Wording example:
`credit_stress is shown as context because liquidity_stress is the dominant escalation.`

**Planned config layer (Step 20A):** `data/config/alert_hierarchy.csv` maps
`environment_state` to dominant/subsumed rule pairs per regime. This file is loaded
and validated by `config_loader` but **does not change runtime behavior yet**.
Runtime still uses the static `ALERT_SUBSUME_BY` map in `rule_engine.py` until
environment classification is wired.

Hard-limit rules (`var_breach`, `drawdown_breach`) must never appear as
`subsumed_rule_id` in the hierarchy config.

---

## 5. Final Escalation

Overall escalation in the after-market report and dashboard ERM summary is:

- **red** if any confirmed rule alert is red
- else **yellow** if any confirmed rule alert is yellow
- else **green**

It is **not** driven by a single metric color alone. Example: several yellow metrics
with only one red confirmed rule (`credit_stress`) yields **overall red** because
the highest **rule** alert is red.

---

## 6. How To Use The Dashboard

### Bloomberg-Style Market Monitor (Tab 1)

- Start with the **Metric Status Board** (Layer 1).
- Identify which metrics are yellow/red and which rules they relate to.
- Use raw metric tiles and latest closes for context.

### Portfolio Risk & Factor Dashboard (Tab 2)

- Review **metric status summary** counts (green/yellow/red).
- Review portfolio drawdown, VaR ratio, and credit proxy.
- Review observable ETF proxy factor exposure and contribution (not Barra).
- Review rule-engine ERM escalation counts (Layer 3 on alerts).

### Strategy Dashboard (Tab 3)

- Read **rule alerts** with escalation color (Layer 2).
- Treat `recommended_action` as **propose / flag for review**, not execution.
- Confirm `requires_human_review` on yellow and red alerts.

---

## 7. How To Use The After-Market Report

Suggested read order:

1. **Executive Risk Summary** - overall escalation and headline
2. **Market Close Snapshot** - key moves and **Metric Status Summary**
3. **Portfolio Risk Readout** - drawdown, VaR, exposures
4. **Factor Risk View** - proxy attribution (prototype)
5. **Strategy and Alert View** - confirmed rules and review actions
6. **Next Trading Day Watchlist** - what to monitor (not predictions)
7. **Governance and No-Look-Ahead Notes**

Generate report:

```bash
python scripts/generate_after_market_report.py
```

Output: `reports/generated/after_market_risk_report_<as_of_date>.md`

---

## 8. Governance

- **No look-ahead:** metrics and alerts use data on or before `as_of_date` only.
- **Sample replay / prototype only** until live feeds are wired and validated.
- **No execution** pathway in this repository.
- **No strategy switch** without backtest and walk-forward evidence in
  `strategy_library.csv` policies.
- **Thresholds require historical calibration** before production or client-facing use.
- Metric status bands and regime thresholds are **monitoring prototypes**, not
  investment advice.

For configuration details see `data/config/regime_thresholds.csv`,
`data/config/metric_status_policy.csv`, and `src/regime/rule_engine.py`.
