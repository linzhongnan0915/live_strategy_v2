"""Hosted web app entrypoint for the live strategy workstation.

This serves the HTML dashboard and optionally runs the polling loop in the same
process. It is designed for Render/Railway/Fly-style web services that require
binding to 0.0.0.0:$PORT.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_live_polling import (  # noqa: E402
    DEFAULT_FRIEND_API_BASE,
    DEFAULT_LIVE_RAW_PATH,
    DEFAULT_MACRO_CONTEXT_PATH,
    DEFAULT_MONITOR_PATH,
    DEFAULT_NEWS_RISK_PATH,
    DEFAULT_PROCESSED_PATH,
    DEFAULT_STATUS_PATH,
    DEFAULT_WATCHLIST_PATH,
    run_poll_cycle,
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    if minimum is not None:
        return max(minimum, value)
    return value


def _polling_config() -> dict[str, Any]:
    return {
        "provider": os.getenv("OPENBB_PROVIDER", "yfinance"),
        "interval_seconds": _env_int("POLLING_INTERVAL_SECONDS", 60, minimum=1),
        "lookback_days": _env_int("LOOKBACK_DAYS", 10, minimum=2),
        "live_raw_path": Path(os.getenv("LIVE_RAW_PATH", str(DEFAULT_LIVE_RAW_PATH))),
        "processed_path": Path(os.getenv("PROCESSED_PATH", str(DEFAULT_PROCESSED_PATH))),
        "monitor_path": Path(os.getenv("MONITOR_PATH", str(DEFAULT_MONITOR_PATH))),
        "watchlist_path": Path(os.getenv("WATCHLIST_PATH", str(DEFAULT_WATCHLIST_PATH))),
        "status_path": Path(os.getenv("STATUS_PATH", str(DEFAULT_STATUS_PATH))),
        "news_risk_path": Path(os.getenv("NEWS_RISK_PATH", str(DEFAULT_NEWS_RISK_PATH))),
        "macro_context_path": Path(os.getenv("MACRO_CONTEXT_PATH", str(DEFAULT_MACRO_CONTEXT_PATH))),
        "news_api_url": os.getenv("NEWS_API_URL") or None,
        "friend_api_base_url": os.getenv("FRIEND_API_BASE_URL", DEFAULT_FRIEND_API_BASE),
        "market_data_mode": os.getenv("MARKET_DATA_MODE", "openbb").strip().lower(),
    }


def _polling_loop() -> None:
    config = _polling_config()
    cycle = 1
    interval = int(config["interval_seconds"])
    market_data_mode = str(config["market_data_mode"])
    if interval < 15 and market_data_mode == "openbb":
        print(
            "warning: hosted OpenBB/yfinance polling below 15s may be rate-limited; "
            "prefer MARKET_DATA_MODE=none for 1s news-only demos.",
            flush=True,
        )

    while True:
        status = run_poll_cycle(cycle=cycle, **config)
        print(
            f"hosted_poll cycle={cycle} status={status.get('status')} "
            f"latest={status.get('latest_observed_date')} rows={status.get('row_count')} "
            f"news={status.get('news_status')} severity={status.get('news_max_severity')}",
            flush=True,
        )
        cycle += 1
        time.sleep(interval)


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", ""}:
            self.send_response(302)
            self.send_header("Location", "/web_dashboard/index.html")
            self.end_headers()
            return
        if self.path == "/healthz":
            payload = (
                "{"
                f'"status":"ok","generated_at_utc":"{datetime.now(timezone.utc).isoformat()}"'
                "}"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()


def main() -> None:
    port = _env_int("PORT", 8600, minimum=1)
    host = os.getenv("HOST", "0.0.0.0")
    polling_enabled = _env_bool("ENABLE_POLLING", True)

    if polling_enabled:
        thread = threading.Thread(target=_polling_loop, name="live-polling", daemon=True)
        thread.start()
        print("hosted polling started", flush=True)
    else:
        print("hosted polling disabled; serving committed/static artifacts only", flush=True)

    handler = partial(DashboardHandler, directory=str(ROOT))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"serving dashboard at http://{host}:{port}/web_dashboard/index.html", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
