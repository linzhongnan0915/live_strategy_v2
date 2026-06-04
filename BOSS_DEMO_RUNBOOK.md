# Boss Demo Runbook

Purpose: explain the live strategy risk workstation clearly in a short review.

## One-Sentence Positioning

This is a multi-sector ETF risk and strategy workstation that combines portfolio monitoring, Barra-style ETF proxy factor risk, BlackRock-style factor-to-assets strategy sleeves, structured news triage, and rolling walk-forward strategy evidence.

## Current Demo Snapshot

- Portfolio base: USD 1,000,000 strategy-guided simulation.
- Simulation start: 2025-01-02.
- Latest dashboard date: 2026-06-03.
- Current selected sleeve: Energy Inflation Shock Rotation.
- Current sleeve ETFs: XLE, USO, TIP, GLD, UUP.
- WFO setup: 5-year training window, 12-month test window, 3-month step, 20 rolling windows.
- Strategy universe: 20 ETF sleeves across macro factor allocation, sector rotation, smart beta, hedge/stress, and completion/liquidity portfolios.

## Links To Share

Replace `YOUR_PUBLIC_URL` after deployment:

- Overview: `https://YOUR_PUBLIC_URL/web_dashboard/index.html`
- Market Monitor: `https://YOUR_PUBLIC_URL/web_dashboard/market.html`
- Risk Factors: `https://YOUR_PUBLIC_URL/web_dashboard/risk.html`
- Strategies: `https://YOUR_PUBLIC_URL/web_dashboard/strategies.html`

## Recommended Demo Flow

1. Start with Overview.
   - Use the four-step decision map: Market risk read -> Portfolio exposure -> Strategy decision -> Governance.
   - Show portfolio value, daily P&L, VaR/ES proxy, max drawdown, and risk limit usage.
   - Hover over the performance and drawdown charts to show weekly date, strategy used, weekly return, and drawdown.
   - Explain that the simulation uses a USD 1,000,000 portfolio starting on 2025-01-02 and avoids look-ahead by selecting strategies from past data only.
   - Point to the current strategy sleeve and next-business-day preview.

2. Move to Market Monitor.
   - Show ETF moves, top movers, worst movers, and monitor-only assets.
   - Explain that this is OpenBB/yfinance prototype market data, not Bloomberg tick data.
   - Use this screen as the live-style market tape: what moved, what is stale, and what data source is feeding the dashboard.

3. Move to Risk Factors.
   - Show risk signals first: volatility, equity, credit, energy, safe-haven, news/event risk.
   - Then show Barra-style factor risk contribution and factor loading matrix.
   - Explain that this is an observable ETF proxy model, not a commercial Barra model.
   - Show news triage: warning level, keywords, affected tickers, affected strategies, confidence, and reasoning.
   - Emphasize that raw news severity alone does not turn the portfolio red; it needs portfolio/strategy mapping or market confirmation.

4. Finish with Strategies.
   - Explain that the strategy decision is not based on total return alone.
   - Show the selected strategy, sleeve holdings, WFO evidence, baseline backtest evidence, and news impact.
   - Show the rolling WFO setup: 5y train / 12m test / 3m step.
   - Explain the decision hierarchy: current market fit first, then WFO evidence, then risk/news confirmation, then human review.
   - Make clear that the output is a manager review direction, not an automatic trade.

## Current Methodology Summary

- Universe: 40 multi-sector ETFs and monitors.
- Strategies: 20 ETF sleeves across macro factors, sectors, smart beta, hedge/stress, and completion portfolios.
- Factor model: observable ETF proxy factor model.
- WFO: rolling train/test evaluation with no look-ahead.
- News: friend API headline triage with portfolio/strategy mapping and market confirmation.
- Risk policy: human review required before any strategy change or allocation action.

## What Not To Overclaim

- Not Bloomberg tick data.
- Not a commercial Barra model.
- Not trade execution.
- Not an investment recommendation.
- Not a production alpha model.
- News severity alone does not authorize escalation.

## Strong Talking Points

- The dashboard separates market monitoring, factor risk, and strategy decisions into three screens.
- The strategy page uses WFO evidence and current market fit, not just past total return.
- The risk page explains why a news item matters or why it is context only.
- The system exposes data quality and no-look-ahead controls instead of hiding assumptions.
- The Overview page can be read as a risk manager workflow: portfolio condition, market/factor risk, strategy implication, and governance.

## Short Spoken Script

This is a prototype ETF risk and strategy workstation. The goal is not to auto-trade, but to help a risk manager see current portfolio condition, factor risk, news relevance, and which strategy sleeve deserves review.

The Overview starts with portfolio condition and risk limit usage. The two main charts are interactive: hovering shows the date, weekly return, drawdown, and strategy used at that point in the no-look-ahead simulation.

The Market screen acts like a simplified Bloomberg-style monitor. It shows ETF moves and data status. The Risk screen translates those moves into factor and event-risk signals. The Strategy screen then connects the market state to a selected ETF sleeve, with WFO and backtest evidence.

The current selected sleeve is Energy Inflation Shock Rotation, expressed through XLE, USO, TIP, GLD, and UUP. The reason is not simply that it had the highest historical return. The framework combines current market fit, rolling WFO evidence, drawdown behavior, news linkage, and human review.

## Current Limitations And Next Steps

- Add transaction costs, slippage, and turnover to strategy backtests.
- Add benchmark comparison versus SPY, 60/40, and policy portfolio.
- Add after-market report v2 using the same artifacts as the dashboard.
- Improve UI polish toward an institutional risk terminal style.
- Replace OpenBB/yfinance with paid or institutional market data when available.
