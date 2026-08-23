from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ai_hedge_fund.alerts.telegram import TelegramNotifier
from ai_hedge_fund.execution.moomoo_order_monitor import MoomooOrderStatus
from ai_hedge_fund.persistence.events import TradeEvent, TradeEventStore
from ai_hedge_fund.portfolio.manager import PositionManager


@dataclass(frozen=True)
class ConfirmedPaperFill:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float


class PaperFillService:
    """Apply confirmed Moomoo paper fills exactly once to local state."""

    def __init__(self, positions: PositionManager, events: TradeEventStore, telegram: TelegramNotifier) -> None:
        self.positions = positions
        self.events = events
        self.telegram = telegram
        self._processed_order_ids: set[str] = set()

    def process(self, *, order_id: str, symbol: str, side: str, status: MoomooOrderStatus) -> ConfirmedPaperFill | None:
        if status.status != "FILLED" or status.filled_quantity <= 0 or status.average_price is None:
            return None
        if order_id in self._processed_order_ids:
            return None

        side = side.upper()
        quantity = status.filled_quantity
        price = status.average_price
        if side == "BUY":
            self.positions.open(symbol, quantity, price)
        elif side == "SELL":
            self.positions.close(symbol)
        else:
            raise ValueError(f"Unsupported trade side: {side}")

        event = TradeEvent(
            event_type="PAPER_TRADE_FILLED",
            trade_id=str(order_id),
            symbol=symbol.upper(),
            side=side,
            quantity=quantity,
            price=price,
            occurred_at=datetime.now(timezone.utc),
            metadata={"order_id": str(order_id), "execution": "MOOMOO_SIMULATE"},
        )
        self.events.save(event)
        self._processed_order_ids.add(str(order_id))
        self.telegram.send_trade_event(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            event="PAPER_TRADE_FILLED",
            order_id=str(order_id),
        )
        return ConfirmedPaperFill(str(order_id), symbol.upper(), side, quantity, price)
