"""Read-only local API for the TradingBot dashboard."""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Import FastAPI lazily so the core trading package has no API dependency."""
    from tradingbot.api.app import create_app as factory

    return factory(*args, **kwargs)
