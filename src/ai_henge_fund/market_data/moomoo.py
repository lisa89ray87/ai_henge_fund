"""Read-only Moomoo market-data boundary.

This module exposes normalized market data only. No order, trading, or account
mutation capability is part of this interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol, Sequence


class MoomooAdapterError(RuntimeError):
    """Raised when the configured Moomoo market-data adapter cannot be used."""


@dataclass(frozen=True, slots=True)
class MoomooQuote:
    symbol: str
    last_price: float | None
    timestamp: datetime | None = None
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    previous_close: float | None = None
    raw: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MoomooCandle:
    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float | None = None
    last_close: float | None = None
    raw: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the normalized candle for the provider-neutral snapshot."""
        return {
            "symbol": self.symbol,
            "time": self.time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "turnover": self.turnover,
            "last_close": self.last_close,
        }


@dataclass(frozen=True, slots=True)
class MoomooMarketState:
    symbol: str
    state: str
    stock_name: str | None = None
    raw: Mapping[str, Any] | None = None


class MoomooTransport(Protocol):
    """Read-only transport contract implemented by OpenD or MCP."""

    def get_quote(self, symbol: str) -> Mapping[str, Any]: ...

    def get_candles(self, symbol: str, num: int, interval: str) -> Sequence[Mapping[str, Any]]: ...

    def get_market_state(self, symbol: str) -> Mapping[str, Any]: ...


class MoomooMarketData:
    """Safe normalized market-data facade for higher-level components."""

    def __init__(self, transport: MoomooTransport | None = None, *, enabled: bool = False) -> None:
        self._transport = transport
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled and self._transport is not None

    def _require_enabled(self) -> MoomooTransport:
        if not self.enabled:
            raise MoomooAdapterError("Moomoo market data is disabled or no transport is configured.")
        assert self._transport is not None
        return self._transport

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized if "." in normalized else f"US.{normalized}"

    def get_quote(self, symbol: str) -> MoomooQuote:
        code = self._symbol(symbol)
        payload = self._require_enabled().get_quote(code)
        return self._normalize_quote(code, payload)

    def get_candles(self, symbol: str, num: int = 100, interval: str = "1d") -> list[MoomooCandle]:
        if num < 1 or num > 1000:
            raise ValueError("num must be between 1 and 1000")
        code = self._symbol(symbol)
        rows = self._require_enabled().get_candles(code, num, interval)
        return [self._normalize_candle(code, row) for row in rows]

    def get_market_state(self, symbol: str) -> MoomooMarketState:
        code = self._symbol(symbol)
        payload = self._require_enabled().get_market_state(code)
        return MoomooMarketState(
            symbol=code,
            state=str(payload.get("market_state", payload.get("state", "UNKNOWN"))),
            stock_name=payload.get("stock_name") or payload.get("name"),
            raw=payload,
        )

    @staticmethod
    def _float(payload: Mapping[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return float(value)
        return None

    @classmethod
    def _normalize_quote(cls, symbol: str, payload: Mapping[str, Any]) -> MoomooQuote:
        timestamp = payload.get("timestamp", payload.get("update_time"))
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = None
        if not isinstance(timestamp, datetime):
            timestamp = None
        volume = payload.get("volume")
        return MoomooQuote(
            symbol=symbol,
            last_price=cls._float(payload, "last_price", "lastPrice", "price"),
            bid=cls._float(payload, "bid", "bid_price", "bidPrice"),
            ask=cls._float(payload, "ask", "ask_price", "askPrice"),
            volume=int(volume) if volume is not None else None,
            open_price=cls._float(payload, "open_price", "open"),
            high_price=cls._float(payload, "high_price", "high"),
            low_price=cls._float(payload, "low_price", "low"),
            previous_close=cls._float(payload, "prev_close_price", "previous_close", "prevClose"),
            timestamp=timestamp,
            raw=payload,
        )

    @classmethod
    def _normalize_candle(cls, symbol: str, payload: Mapping[str, Any]) -> MoomooCandle:
        raw_time = payload.get("time_key", payload.get("time"))
        if isinstance(raw_time, datetime):
            candle_time = raw_time
        elif isinstance(raw_time, str):
            candle_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        else:
            raise MoomooAdapterError("Moomoo candle has no valid time_key.")
        return MoomooCandle(
            symbol=symbol,
            time=candle_time,
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=int(payload.get("volume", 0)),
            turnover=cls._float(payload, "turnover"),
            last_close=cls._float(payload, "last_close"),
            raw=payload,
        )
