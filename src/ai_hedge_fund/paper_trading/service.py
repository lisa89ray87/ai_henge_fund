from __future__ import annotations

from ai_hedge_fund.alerts.telegram import TelegramNotifier
from ai_hedge_fund.paper_trading.engine import PaperTrade, PaperTradingEngine


class PaperTradeService:
    """Executes a paper trade and emits a Telegram event notification."""

    def __init__(self, engine: PaperTradingEngine, telegram: TelegramNotifier | None = None) -> None:
        self.engine = engine
        self.telegram = telegram

    def execute(self, *, symbol: str, side: str, quantity: float, price: float, metadata: dict[str, object] | None = None) -> PaperTrade:
        trade = self.engine.execute(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            metadata=metadata,
        )
        if self.telegram is not None:
            self.telegram.send_trade_event(
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                event="PAPER_TRADE",
                order_id=trade.trade_id,
            )
        return trade
