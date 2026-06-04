"""Hosted web app entrypoint for the live strategy workstation.

This serves the HTML dashboard and optionally runs the polling loop in the same
process. It is designed for Render/Railway/Fly-style web services that require
binding to 0.0.0.0:$PORT.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def _start_polling_process() -> subprocess.Popen:
    """Run polling as a child process so yfinance/OpenBB can use main-thread signals."""
    cmd = _polling_command()
    print("hosted polling subprocess command:", " ".join(cmd), flush=True)
    return subprocess.Popen(cmd, cwd=str(ROOT))


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
        _start_polling_process()
        print("hosted polling started in child process", flush=True)
    else:
        print("hosted polling disabled; serving committed/static artifacts only", flush=True)

    handler = partial(DashboardHandler, directory=str(ROOT))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"serving dashboard at http://{host}:{port}/web_dashboard/index.html", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
