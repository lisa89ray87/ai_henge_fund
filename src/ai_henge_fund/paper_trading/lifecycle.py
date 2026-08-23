from __future__ import annotations

from dataclasses import dataclass

from ai_henge_fund.alerts.telegram import TelegramNotifier
from ai_henge_fund.paper_trading.engine import PaperTradingEngine, PaperTrade
from ai_henge_fund.portfolio.manager import PositionManager


@dataclass(frozen=True)
class TradeLifecycleResult:
    action: str
    trade: PaperTrade | None
    reason: str


class PaperTradeLifecycle:
    """Coordinates paper execution with position state and notifications."""

    def __init__(self, engine: PaperTradingEngine, positions: PositionManager, telegram: TelegramNotifier | None = None) -> None:
        self.engine = engine
        self.positions = positions
        self.telegram = telegram

    def open(self, *, symbol: str, side: str, quantity: float, price: float) -> TradeLifecycleResult:
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            return TradeLifecycleResult("WAIT", None, "Unsupported opening side")
        if self.positions.get(symbol) is not None:
            return TradeLifecycleResult("WAIT", None, "Position already open")

        trade = self.engine.execute(symbol=symbol, side=side, quantity=quantity, price=price)
        self.positions.open(symbol, quantity, price)
        self._notify(trade, "PAPER_OPEN")
        return TradeLifecycleResult("OPEN", trade, "Position opened")

    def close(self, *, symbol: str, price: float) -> TradeLifecycleResult:
        position = self.positions.get(symbol)
        if position is None:
            return TradeLifecycleResult("WAIT", None, "No open position")

        closing_side = "SELL" if position.quantity > 0 else "BUY"
        trade = self.engine.execute(symbol=symbol, side=closing_side, quantity=abs(position.quantity), price=price)
        self.positions.close(symbol)
        self._notify(trade, "PAPER_CLOSE")
        return TradeLifecycleResult("CLOSE", trade, "Position closed")

    def _notify(self, trade: PaperTrade, event: str) -> None:
        if self.telegram is not None:
            self.telegram.send_trade_event(
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                event=event,
                order_id=trade.trade_id,
            )
