"""Hosted web app entrypoint for the live strategy workstation.

This serves the HTML dashboard and optionally runs the polling loop in the same
process. It is designed for Render/Railway/Fly-style web services that require
binding to 0.0.0.0:$PORT.
"""

from __future__ import annotations

import os
import subprocess
import sys
import json
import threading
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATUS_PATH = ROOT / "output" / "live_polling_status.json"
CHILD_RESTART_SECONDS = 10


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

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


def _polling_command() -> list[str]:
    cmd = [
        sys.executable,
        "scripts/run_live_polling.py",
        "--provider",
        os.getenv("OPENBB_PROVIDER", "yfinance"),
        "--interval-seconds",
        str(_env_int("POLLING_INTERVAL_SECONDS", 60, minimum=1)),
        "--lookback-days",
        str(_env_int("LOOKBACK_DAYS", 10, minimum=2)),
        "--market-data-mode",
        os.getenv("MARKET_DATA_MODE", "openbb").strip().lower(),
        "--friend-api-base-url",
        os.getenv("FRIEND_API_BASE_URL", "https://news.tcx086.com"),
    ]
    news_api_url = os.getenv("NEWS_API_URL")
    if news_api_url:
        cmd.extend(["--news-api-url", news_api_url])
    return cmd


def _write_hosted_polling_status(
    *,
    status: str,
    message: str,
    error: str | None = None,
) -> None:
    """Write a visible hosted status before/after the polling child runs.

    The polling child overwrites this file after a real cycle. This bootstrap
    file prevents deployed dashboards from showing 404 when the child has not
    produced its first artifact yet, and it makes child-process failures visible.
    """
    market_data_mode = os.getenv("MARKET_DATA_MODE", "openbb").strip().lower()
    interval_seconds = _env_int("POLLING_INTERVAL_SECONDS", 60, minimum=1)
    payload = {
        "generated_at_utc": _utc_now(),
        "status": status,
        "cycle": 0,
        "message": message,
        "provider": os.getenv("OPENBB_PROVIDER", "yfinance")
        if market_data_mode == "openbb"
        else "none",
        "market_data_mode": market_data_mode,
        "market_data_active": market_data_mode == "openbb",
        "interval_seconds": interval_seconds,
        "next_poll_after_utc": None,
        "ticker_count": 0,
        "configured_market_ticker_count": 0,
        "row_count": 0,
        "latest_observed_date": None,
        "news_status": None,
        "news_max_severity": None,
        "error": error,
        "data_mode": "hosted_polling_bootstrap",
        "official_risk_decision_allowed": False,
        "note": (
            "Hosted polling process is starting or recovering. "
            "This bootstrap status is replaced after the first successful poll."
        ),
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _start_polling_process() -> subprocess.Popen:
    """Run polling as a child process so yfinance/OpenBB can use main-thread signals."""
    cmd = _polling_command()
    print("hosted polling subprocess command:", " ".join(cmd), flush=True)
    return subprocess.Popen(cmd, cwd=str(ROOT))


def _polling_supervisor() -> None:
    """Keep hosted polling alive and surface child failures to the dashboard."""
    while True:
        _write_hosted_polling_status(
            status="starting",
            message="hosted polling child process is starting",
        )
        process = _start_polling_process()
        print(f"hosted polling child pid={process.pid}", flush=True)
        exit_code = process.wait()
        error = f"hosted polling child exited with code {exit_code}"
        print(error, flush=True)
        _write_hosted_polling_status(
            status="failed",
            message="hosted polling child process exited; supervisor will restart it",
            error=error,
        )
        time.sleep(CHILD_RESTART_SECONDS)


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", ""}:
            self.send_response(302)
            self.send_header("Location", "/web_dashboard/index.html")
            self.end_headers()
            return
        if path == "/healthz":
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
        supervisor = threading.Thread(
            target=_polling_supervisor,
            name="hosted-polling-supervisor",
            daemon=True,
        )
        supervisor.start()
        print("hosted polling supervisor started", flush=True)
    else:
        _write_hosted_polling_status(
            status="disabled",
            message="hosted polling disabled; serving committed/static artifacts only",
        )
        print("hosted polling disabled; serving committed/static artifacts only", flush=True)

    handler = partial(DashboardHandler, directory=str(ROOT))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"serving dashboard at http://{host}:{port}/web_dashboard/index.html", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
