# Live Strategy V2 UI Direction

Purpose: keep the existing risk/strategy/data logic, but redesign the dashboard
UI into a more institutional financial risk terminal style.

## What V2 Should Preserve

- Existing ETF universe, holdings, strategy library, WFO/backtest outputs.
- Existing rule engine, escalation logic, metric status logic, and data quality gates.
- Existing friend-news ingestion and explainable risk/news triage standards.
- Existing non-Streamlit deployment direction.

## What V2 Should Improve

- Visual style should follow a professional dark financial risk terminal:
  - dark navy / black background
  - compact KPI cards
  - dense but readable tables
  - heatmaps, line charts, drawdown charts, allocation charts
  - restrained red/yellow/green risk signaling
  - clear timestamps and data-source labels
- No decorative map requirement.
- No unsupported AI commentary.
- News signals must include timestamp, source, affected exposure, reasoning,
  confidence, and whether the signal is monitor-only, review, or escalation.

## Target Page Structure

1. Overview / Market Monitor
2. Risk Analytics / Factor Risk
3. Strategy Decision Board
4. News & Signal Intelligence
5. Positions / Holdings
6. Backtest & Walk-Forward Evidence
7. Stress Testing
8. End-of-Day Review

## Design Reference

Use the user's preferred financial risk dashboard screenshot as the primary
visual reference. Use the situation-monitor project only as a reference for
component organization, service patterns, badges, panels, caching, and news
deduplication. Do not copy its map-centric design.

## Non-Negotiables

- Do not overwrite the original `D:\Global_Ai\live_strategy` demo.
- Do not fabricate news or market signals.
- Do not rank strategies by total return alone.
- Do not treat prototype outputs as trade execution instructions.
- Keep every decision-oriented output tied to data, source, timestamp, metric,
  or explicit assumption.
