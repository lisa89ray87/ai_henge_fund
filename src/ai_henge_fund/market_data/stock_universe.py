"""Default liquid U.S. stock universe for the Moomoo signal scanner."""

from __future__ import annotations

import os

DEFAULT_US_STOCK_UNIVERSE = (
    "US.NVDA",
    "US.AMD",
    "US.INTC",
    "US.AAPL",
    "US.MSFT",
    "US.AMZN",
    "US.META",
    "US.TSLA",
    "US.GOOGL",
    "US.AVGO",
    "US.MU",
    "US.SNDK",
    "US.PLTR",
    "US.DDOG",
    "US.CRWD",
    "US.ARM",
    "US.QCOM",
    "US.SMCI",
    "US.NFLX",
    "US.NOK",
)


def get_stock_universe() -> list[str]:
    """Return the configured universe, preserving an explicit single-symbol override."""
    symbol = os.getenv("MOOMOO_SIGNAL_SYMBOL", "").strip().upper()
    if symbol:
        return [symbol]

    configured = os.getenv("MOOMOO_SIGNAL_UNIVERSE", "").strip()
    if configured:
        values = [item.strip().upper() for item in configured.split(",") if item.strip()]
        if values:
            return list(dict.fromkeys(values))

    return list(DEFAULT_US_STOCK_UNIVERSE)
