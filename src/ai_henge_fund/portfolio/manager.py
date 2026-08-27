from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    average_price: float
    opened_at: datetime


class PositionManager:
    """In-memory paper position state with duplicate-entry protection."""

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    def get(self, symbol: str) -> Position | None:
        return self._positions.get(symbol.strip().upper())

    def can_open(self, symbol: str, side: str) -> bool:
        return self.get(symbol) is None

    def open(self, symbol: str, quantity: float, price: float) -> Position:
        """Open a long-compatible positive position for backwards compatibility."""
        return self.open_signed(symbol, quantity, price)

    def open_signed(self, symbol: str, quantity: float, price: float) -> Position:
        """Open a signed paper position; positive=long, negative=short."""
        symbol = symbol.strip().upper()
        if self.get(symbol) is not None:
            raise ValueError(f"position already open for {symbol}")
        if quantity == 0 or price <= 0:
            raise ValueError("non-zero quantity and positive price are required")
        position = Position(symbol, quantity, price, datetime.now(timezone.utc))
        self._positions[symbol] = position
        return position

    def close(self, symbol: str) -> Position:
        symbol = symbol.strip().upper()
        position = self._positions.pop(symbol, None)
        if position is None:
            raise ValueError(f"no open position for {symbol}")
        return position
