# Live Strategy Workstation Run Guide

This project currently uses the non-Streamlit web dashboard:

- `web_dashboard/market.html`
- `web_dashboard/risk.html`
- `web_dashboard/strategies.html`

The pages read the latest JSON artifacts from `output/` and update the displayed data without refreshing the full page.

## 1. Start The Workstation

Open PowerShell:

```powershell
cd D:\Global_Ai\live_strategy_v2

.\scripts\run_web_workstation.ps1 `
  -StartPolling `
  -PollingIntervalSeconds 15 `
  -MarketDataMode openbb `
  -NewsApiUrl "https://news.tcx086.com/analysis/patterns"
```

This starts:

- local web dashboard server
- OpenBB/yfinance market polling
- friend API news polling

## 2. Open The Three Screens

Market Monitor:

```text
http://localhost:8600/web_dashboard/market.html
```

Risk Factors:

```text
http://localhost:8600/web_dashboard/risk.html
```

Strategies:

```text
http://localhost:8600/web_dashboard/strategies.html
```

## 3. Generate After-Market Strategy Review

Run this after market close or before a demo if you want the Strategy screen to show a generated daily review artifact:

```powershell
cd D:\Global_Ai\live_strategy_v2
python scripts\build_daily_strategy_review.py
```

Output:

```text
output/daily_strategy_review_snapshot.json
```

## 4. Stop The Workstation

```powershell
cd D:\Global_Ai\live_strategy_v2
.\scripts\stop_live_workstation.ps1
```

This stops the local dashboard server and live polling processes for this project.

## 5. If The Page Looks Stale

Use hard refresh:

```text
Ctrl + F5
```

## 6. Important Notes

- This is a prototype risk workstation, not Bloomberg.
- OpenBB/yfinance is used as an accessible market data prototype.
- The dashboard does not execute trades.
- Strategy outputs are review candidates only.
- Human review is required before any strategy decision.
- For true tick-by-tick live market data, a real quote API or WebSocket feed is needed.

## 7. Create A Temporary Shareable Link

Use this when you need to send the dashboard to someone outside your machine.

```powershell
cd D:\Global_Ai\live_strategy_v2

.\scripts\share_web_workstation.ps1 `
  -StartPolling `
  -PollingIntervalSeconds 15 `
  -MarketDataMode openbb `
  -NewsApiUrl "https://news.tcx086.com/analysis/patterns"
```

The script prints one landing page link and three direct screen links.

Important:

- Keep your computer on while the link is being reviewed.
- The `trycloudflare.com` link is temporary.
- Stop sharing with:

```powershell
.\scripts\stop_live_workstation.ps1
```

## 8. Publish An Always-Open Website

There are two deployment modes:

### Static snapshot

Use this when the boss needs a link today and can review the current dashboard state.

```powershell
cd D:\Global_Ai\live_strategy_v2
python scripts\build_factor_risk_snapshot.py
python scripts\walk_forward_strategies_demo.py
python scripts\simulate_strategy_portfolio.py
python scripts\prepare_web_snapshots.py
python scripts\check_deployment_readiness.py
```

Then deploy `web_dashboard/` with the committed `web_dashboard/snapshots/`
folder to GitHub Pages or Cloudflare Pages.

Limitation: this does not run live polling by itself.

### Hosted live-style service

Use this when the boss needs the website to stay open online and update without
your laptop running.

Cloud service start command:

```text
python scripts/run_hosted_web_app.py
```

Recommended environment variables:

```text
ENABLE_POLLING=true
POLLING_INTERVAL_SECONDS=60
MARKET_DATA_MODE=none
NEWS_API_URL=https://news.tcx086.com/analysis/patterns
FRIEND_API_BASE_URL=https://news.tcx086.com
```

Use `MARKET_DATA_MODE=none` for the first public deployment so the site is
stable and news can update live. After the hosted website works, switch to
`MARKET_DATA_MODE=openbb` only if the cloud logs show OpenBB/yfinance is working
reliably.

Direct hosted paths:

```text
/web_dashboard/index.html
/web_dashboard/market.html
/web_dashboard/risk.html
/web_dashboard/strategies.html
```
