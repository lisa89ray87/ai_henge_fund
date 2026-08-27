from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    average_price: float
    opened_at: datetime
    stop_price: float | None = None
    target_price: float | None = None


class PositionManager:
    """In-memory paper position state with broker-session reconciliation."""

    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    def get(self, symbol: str) -> Position | None:
        return self._positions.get(symbol.strip().upper())

    def all(self) -> list[Position]:
        return list(self._positions.values())

    def can_open(self, symbol: str, side: str) -> bool:
        return self.get(symbol) is None

    def open(self, symbol: str, quantity: float, price: float) -> Position:
        return self.open_signed(symbol, quantity, price)

    def open_signed(self, symbol: str, quantity: float, price: float,
                    *, stop_price: float | None = None, target_price: float | None = None,
                    opened_at: datetime | None = None) -> Position:
        symbol = symbol.strip().upper()
        if self.get(symbol) is not None:
            raise ValueError(f"position already open for {symbol}")
        if quantity == 0 or price <= 0:
            raise ValueError("non-zero quantity and positive price are required")
        position = Position(
            symbol, quantity, price, opened_at or datetime.now(timezone.utc),
            stop_price=stop_price, target_price=target_price,
        )
        self._positions[symbol] = position
        return position

    def restore(self, symbol: str, quantity: float, price: float, *,
                stop_price: float | None = None, target_price: float | None = None,
                opened_at: datetime | None = None) -> Position:
        """Restore broker state without treating it as a new entry."""
        symbol = symbol.strip().upper()
        if quantity == 0:
            self._positions.pop(symbol, None)
            raise ValueError("cannot restore a zero-quantity position")
        position = Position(
            symbol, quantity, price, opened_at or datetime.now(timezone.utc),
            stop_price=stop_price, target_price=target_price,
        )
        self._positions[symbol] = position
        return position

    def close(self, symbol: str) -> Position:
        symbol = symbol.strip().upper()
        position = self._positions.pop(symbol, None)
        if position is None:
            raise ValueError(f"no open position for {symbol}")
        return position
