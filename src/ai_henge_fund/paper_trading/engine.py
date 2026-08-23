from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class PaperTrade:
    trade_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    executed_at: datetime
    status: str = "FILLED"
    metadata: dict[str, object] = field(default_factory=dict)


class PaperTradingEngine:
    """Deterministic paper execution boundary.

    This engine never connects to a broker and never places live orders.
    """

    def execute(self, *, symbol: str, side: str, quantity: float, price: float, metadata: dict[str, object] | None = None) -> PaperTrade:
        symbol = symbol.strip().upper()
        side = side.strip().upper()
        if not symbol:
            raise ValueError("symbol must not be empty")
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if price <= 0:
            raise ValueError("price must be greater than zero")

        return PaperTrade(
            trade_id=f"paper-{uuid4().hex[:12]}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            executed_at=datetime.now(timezone.utc),
            metadata=dict(metadata or {}),
        )
