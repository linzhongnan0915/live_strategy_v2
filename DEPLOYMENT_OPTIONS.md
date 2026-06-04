# Deployment Options For Shareable Dashboard

The boss asked for an online shareable dashboard link. There are two different goals:

1. Always openable website
2. Always openable website with live-updating market/news data

These are not the same.

## Option A: GitHub Pages / Cloudflare Pages Static Site

Best for:

- Always openable link
- Reviewing current dashboard layout
- Reviewing latest committed snapshots

Limitations:

- It cannot run OpenBB polling by itself.
- It will not update market/news data unless new JSON artifacts are committed or uploaded.
- Good for an online prototype, not true live monitoring.

Use this if the immediate goal is to share something today.

Before publishing a static site, run:

```powershell
python scripts\build_factor_risk_snapshot.py
python scripts\walk_forward_strategies_demo.py
python scripts\simulate_strategy_portfolio.py
python scripts\prepare_web_snapshots.py
```

The static pages use `web_dashboard/snapshots/` as a fallback because `output/`
is intentionally gitignored.

## Option B: Cloudflare Tunnel From Local Machine

Best for:

- Quick live demo
- Real local polling while your computer is on

Limitations:

- Your computer must stay on.
- The tunnel process must keep running.
- The link is temporary.

Use this for quick review calls, not permanent sharing.

## Option C: Hosted Backend + Static Frontend

Best for:

- Always openable link
- Live-updating data
- Boss can review without your laptop running

Recommended architecture:

- Frontend: Cloudflare Pages or GitHub Pages
- Backend/polling worker: Render, Railway, Fly.io, VPS, or Cloudflare Worker
- Data artifacts: cloud storage, database, or API endpoint
- Update cadence: 15s to 60s for market prototype, faster only for lightweight news/API feeds

This is the correct production direction.

This project now includes a simple hosted entrypoint:

```bash
python scripts/run_hosted_web_app.py
```

Environment variables:

- `PORT`: public web service port
- `ENABLE_POLLING`: `true` or `false`
- `POLLING_INTERVAL_SECONDS`: default `60`
- `MARKET_DATA_MODE`: `openbb` or `none`
- `NEWS_API_URL`: optional friend/news endpoint
- `FRIEND_API_BASE_URL`: default `https://news.tcx086.com`

Render-style deploy:

- Build command: `pip install -r requirements.txt && python scripts/prepare_web_snapshots.py`
- Start command: `python scripts/run_hosted_web_app.py`
- Public URLs after deploy:
  - `/web_dashboard/index.html`
  - `/web_dashboard/market.html`
  - `/web_dashboard/risk.html`
  - `/web_dashboard/strategies.html`

## Recommendation

For the internship demo:

1. Use the current local web dashboard for development.
2. Deploy a static version to GitHub Pages or Cloudflare Pages for an always-open snapshot.
3. Deploy `scripts/run_hosted_web_app.py` on Render/Railway/Fly/VPS for an always-open live-style service.
4. Use Cloudflare Tunnel only for temporary local live demos.

Important: Streamlit is not required for the current web dashboard. The current dashboard is plain HTML/CSS/JS reading JSON artifacts.
