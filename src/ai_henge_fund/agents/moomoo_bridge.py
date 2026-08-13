"""Stable market-data boundary for Moomoo MCP integration.

The application must not depend on a particular MCP server implementation.
A runtime adapter can implement ``MoomooMarketDataProvider`` using the
available Moomoo MCP tools. This keeps provider changes isolated and makes
read-only/paper operation the default architecture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class QuoteSnapshot:
    """Normalized quote data consumed by the AI decision layer."""

    symbol: str
    price: float | None
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    timestamp: datetime | None = None
    market_session: str | None = None
    provider: str = "moomoo-mcp"


class MoomooMarketDataProvider(Protocol):
    """Provider-neutral contract for Moomoo MCP market data."""

    def get_quote(self, symbol: str) -> QuoteSnapshot: ...


class UnconfiguredMoomooProvider:
    """Explicitly disabled provider used until MCP wiring is configured."""

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        raise RuntimeError(
            "Moomoo MCP provider is not configured. Configure the MCP adapter "
            "before enabling live market-data enrichment."
        )


def normalize_quote(payload: dict[str, Any], *, symbol: str) -> QuoteSnapshot:
    """Normalize a provider payload without leaking MCP-specific field names."""
    return QuoteSnapshot(
        symbol=symbol.upper(),
        price=_number(payload.get("price")),
        bid=_number(payload.get("bid")),
        ask=_number(payload.get("ask")),
        volume=_integer(payload.get("volume")),
        timestamp=payload.get("timestamp"),
        market_session=payload.get("market_session"),
    )


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
