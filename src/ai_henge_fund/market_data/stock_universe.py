"""Broad liquid U.S. stock universe for day-trading signal discovery."""

from __future__ import annotations

import os

# Broad cross-exchange universe: high-liquidity names plus stocks that commonly
# exhibit meaningful intraday movement. This is intentionally broader than a
# Nasdaq-only technology list while remaining small enough for OpenD scanning.
DEFAULT_US_STOCK_UNIVERSE = (
    "US.NVDA", "US.AMD", "US.INTC", "US.AAPL", "US.MSFT", "US.AMZN", "US.META", "US.TSLA",
    "US.GOOGL", "US.AVGO", "US.MU", "US.SNDK", "US.PLTR", "US.DDOG", "US.CRWD", "US.ARM",
    "US.QCOM", "US.SMCI", "US.NFLX", "US.NOK",
    "US.MSTR", "US.COIN", "US.MARA", "US.RIOT", "US.TSM", "US.BABA", "US.PDD", "US.TCEHY",
    "US.XOM", "US.CVX", "US.JPM", "US.BAC", "US.WFC", "US.C", "US.GS", "US.MS",
    "US.UBER", "US.LYFT", "US.ABK", "US.RIVN", "US.LCID", "US.NIO", "US.BA", "US.GE",
    "US.CAT", "US.DE", "US.CRM", "US.ORCL", "US.ADBE", "US.PYPL", "US.SQ", "US.SOFI",
    "US.TTD", "US.TXN", "US.MRVL", "US.TSM", "US.TGT", "US.WMT", "US.COST", "US.DIS",
)


def get_stock_universe() -> list[str]:
    """Return the configured universe, preserving explicit overrides."""
    symbol = os.getenv("MOOMOO_SIGNAL_SYMBOL", "").strip().upper()
    if symbol:
        return [symbol]

    configured = os.getenv("MOOMOO_SIGNAL_UNIVERSE", "").strip()
    if configured and configured.lower() != "default":
        values = [item.strip().upper() for item in configured.split(",") if item.strip()]
        if values:
            return list(dict.fromkeys(values))

    return list(dict.fromkeys(DEFAULT_US_STOCK_UNIVERSE))
