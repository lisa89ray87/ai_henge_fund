"""Read-only Moomoo market-data boundary.

The adapter deliberately contains no order/trading methods.  The concrete MCP
transport can be supplied later without coupling the signal/risk layers to a
specific MCP client implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol


class MoomooAdapterError(RuntimeError):
    """Raised when the configured Moomoo market-data adapter cannot be used."""


@dataclass(frozen=True, slots=True)
class MoomooQuote:
    """Normalized read-only quote returned to the AI Henge Fund."""

    symbol: str
    last_price: float | None
    timestamp: datetime | None = None
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    raw: Mapping[str, Any] | None = None


class MoomooTransport(Protocol):
    """Minimal transport contract for a real Moomoo MCP implementation."""

    def get_quote(self, symbol: str) -> Mapping[str, Any]:
        """Return one quote payload for ``symbol`` without placing an order."""


class MoomooMarketData:
    """Safe market-data facade used by higher-level AI Henge Fund components.

    ``transport`` is injected so tests and future MCP transports do not require
    a running Moomoo OpenD process.  No write/order operation is exposed here.
    """

    def __init__(self, transport: MoomooTransport | None = None, *, enabled: bool = False) -> None:
        self._transport = transport
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether the adapter is configured for live read-only quote access."""
        return self._enabled and self._transport is not None

    def get_quote(self, symbol: str) -> MoomooQuote:
        """Fetch and normalize a quote through the injected read-only transport."""
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        if not self.enabled:
            raise MoomooAdapterError(
                "Moomoo market data is disabled or no MCP transport is configured."
            )

        payload = self._transport.get_quote(normalized_symbol)
        return self._normalize_quote(normalized_symbol, payload)

    @staticmethod
    def _normalize_quote(symbol: str, payload: Mapping[str, Any]) -> MoomooQuote:
        """Normalize common quote field names while retaining the raw payload."""
        last = payload.get("last_price", payload.get("lastPrice", payload.get("price")))
        bid = payload.get("bid", payload.get("bid_price", payload.get("bidPrice")))
        ask = payload.get("ask", payload.get("ask_price", payload.get("askPrice")))
        volume = payload.get("volume")
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = None
        if not isinstance(timestamp, datetime):
            timestamp = None

        return MoomooQuote(
            symbol=symbol,
            last_price=float(last) if last is not None else None,
            bid=float(bid) if bid is not None else None,
            ask=float(ask) if ask is not None else None,
            volume=int(volume) if volume is not None else None,
            timestamp=timestamp,
            raw=payload,
        )
