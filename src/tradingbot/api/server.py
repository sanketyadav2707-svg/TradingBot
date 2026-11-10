"""Local-only command for serving the read-only dashboard API."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local read-only TradingBot dashboard API.")
    parser.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install the API extra first: python -m pip install -e '.[api]'") from exc

    from tradingbot.api.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
