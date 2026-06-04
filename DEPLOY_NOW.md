# Deploy Now: Shareable Live Strategy Website

Goal: publish the three-screen dashboard so the boss can open it from a public
URL without your laptop running.

## What Will Be Live First

- Website: live public URL
- News/event risk: live polling from friend API
- Market/risk/strategy data: latest committed dashboard snapshots

Why: OpenBB/yfinance is a prototype market feed. On cloud deployment, start
with a stable website first, then enable OpenBB cloud polling after the URL is
working.

## 1. Refresh Dashboard Snapshots

Run locally before pushing:

```powershell
cd D:\Global_Ai\live_strategy_v2
python scripts\build_factor_risk_snapshot.py
python scripts\walk_forward_strategies_demo.py
python scripts\simulate_strategy_portfolio.py
python scripts\prepare_web_snapshots.py
python scripts\check_deployment_readiness.py
```

## 2. Upload To GitHub

If this folder is not a git repository yet:

```powershell
cd D:\Global_Ai\live_strategy_v2
git init
git add README.md RUN_WORKSTATION.md DEPLOYMENT_OPTIONS.md DEPLOY_NOW.md render.yaml requirements.txt
git add data/config src scripts tests reports web_dashboard
git commit -m "Prepare shareable live strategy web dashboard"
```

Then create a GitHub repo and push:

```powershell
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/live_strategy.git
git push -u origin main
```

Do not use `git add .` unless you first confirm no secrets, raw data, processed
data, logs, or generated reports are included.

## 3. Deploy On Render

Create a Render Web Service from the GitHub repo.

Use the checked-in `render.yaml` if Render detects it, or set:

```text
Build Command:
pip install -r requirements.txt && python scripts/prepare_web_snapshots.py

Start Command:
python scripts/run_hosted_web_app.py
```

Environment variables:

```text
ENABLE_POLLING=true
POLLING_INTERVAL_SECONDS=60
MARKET_DATA_MODE=none
NEWS_API_URL=https://news.tcx086.com/analysis/patterns
FRIEND_API_BASE_URL=https://news.tcx086.com
```

## 4. Share These Links

After Render gives you a URL, share:

```text
https://YOUR-RENDER-APP.onrender.com/web_dashboard/index.html
https://YOUR-RENDER-APP.onrender.com/web_dashboard/market.html
https://YOUR-RENDER-APP.onrender.com/web_dashboard/risk.html
https://YOUR-RENDER-APP.onrender.com/web_dashboard/strategies.html
```

## 5. Optional: Enable OpenBB Cloud Market Polling Later

After the website works, switch:

```text
MARKET_DATA_MODE=openbb
```

Only do this after confirming cloud logs show OpenBB/yfinance works reliably.
If cloud market polling fails, switch back to:

```text
MARKET_DATA_MODE=none
```

The website will still show the latest committed market/risk/strategy snapshots
and live news context.
