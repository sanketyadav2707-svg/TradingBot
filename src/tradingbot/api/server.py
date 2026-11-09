"""Local-only Uvicorn entry point for the dashboard API."""

from __future__ import annotations

import os


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - installation-specific path
        raise SystemExit(
            'Install the API extra first: python -m pip install -e ".[api]"'
        ) from exc

    port = int(os.getenv("TRADINGBOT_API_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("TRADINGBOT_API_PORT must be between 1 and 65535")
    uvicorn.run(
        "tradingbot.api.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        access_log=True,
    )


if __name__ == "__main__":  # pragma: no cover - console-script entry point
    main()
