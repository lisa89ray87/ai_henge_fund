from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class SignalSnapshot:
    """Provider-neutral market snapshot for deterministic engines and TradingAgents.

    The snapshot deliberately carries data quality and source metadata so downstream
    AI reasoning cannot silently treat limited market data as authoritative.
    """

    symbol: str
    timestamp: datetime | None
    last_price: float | None
    volume: float | None
    market_state: str | None
    candles: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    data_source: str = "unknown"
    data_quality: str = "UNKNOWN"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        return bool(self.symbol and self.last_price is not None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "last_price": self.last_price,
            "volume": self.volume,
            "market_state": self.market_state,
            "candles": [dict(candle) for candle in self.candles],
            "data_source": self.data_source,
            "data_quality": self.data_quality,
            "metadata": dict(self.metadata),
        }


def build_signal_snapshot(
    *,
    symbol: str,
    quote: Any,
    market_state: Any | None = None,
    candles: tuple[Any, ...] | list[Any] = (),
    data_source: str = "moomoo_opend",
) -> SignalSnapshot:
    """Convert normalized market-data objects into the shared snapshot contract."""

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")

    candle_dicts: list[Mapping[str, Any]] = []
    for candle in candles:
        if hasattr(candle, "to_dict"):
            candle_dicts.append(candle.to_dict())
        elif isinstance(candle, Mapping):
            candle_dicts.append(dict(candle))
        else:
            raise TypeError("candles must contain mappings or objects exposing to_dict()")

    state_value = getattr(market_state, "state", None)
    quality = "LIVE" if quote is not None else "UNAVAILABLE"

    return SignalSnapshot(
        symbol=normalized_symbol,
        timestamp=getattr(quote, "timestamp", None),
        last_price=getattr(quote, "last_price", None),
        volume=getattr(quote, "volume", None),
        market_state=state_value,
        candles=tuple(candle_dicts),
        data_source=data_source,
        data_quality=quality,
    )
