# Boss Demo Runbook

Purpose: explain the live strategy risk workstation clearly in a short review.

## One-Sentence Positioning

This is a multi-sector ETF risk and strategy workstation that combines portfolio monitoring, Barra-style ETF proxy factor risk, BlackRock-style factor-to-assets strategy sleeves, structured news triage, and rolling walk-forward strategy evidence.

## Links To Share

Replace `YOUR_PUBLIC_URL` after deployment:

- Overview: `https://YOUR_PUBLIC_URL/web_dashboard/index.html`
- Market Monitor: `https://YOUR_PUBLIC_URL/web_dashboard/market.html`
- Risk Factors: `https://YOUR_PUBLIC_URL/web_dashboard/risk.html`
- Strategies: `https://YOUR_PUBLIC_URL/web_dashboard/strategies.html`

## Recommended Demo Flow

1. Start with Overview.
   - Show portfolio value, daily P&L, VaR/ES proxy, max drawdown, risk limit usage.
   - Explain that the portfolio simulation starts from USD 1,000,000 on 2025-01-02.
   - Point to the selected current strategy sleeve and next-business-day preview.

2. Move to Risk Factors.
   - Show live risk signals first: volatility, equity, credit, energy, safe-haven, news.
   - Then show Barra-style factor risk contribution.
   - Explain that this is an observable ETF proxy model, not a commercial Barra model.
   - Show news triage: keywords, affected ETFs, affected strategies, confidence, and reasoning.

3. Finish with Strategies.
   - Explain that strategy ranking is not based on total return alone.
   - Show current selected strategy, WFO evidence, sleeve holdings, and news impact.
   - Show the rolling WFO setup: 5y train / 12m test / 3m step.
   - Show data reliability: source, coverage, duplicate policy, and observation counts.

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

## Current Limitations And Next Steps

- Add transaction costs, slippage, and turnover to strategy backtests.
- Add benchmark comparison versus SPY, 60/40, and policy portfolio.
- Add after-market report v2 using the same artifacts as the dashboard.
- Improve UI polish toward an institutional risk terminal style.
- Replace OpenBB/yfinance with paid or institutional market data when available.
