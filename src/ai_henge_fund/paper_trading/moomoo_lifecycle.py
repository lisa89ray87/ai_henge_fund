from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ai_henge_fund.alerts.telegram import TelegramNotifier
from ai_henge_fund.execution.moomoo_order_monitor import (
    FILLED_ALL,
    MoomooPaperOrderMonitor,
)
from ai_henge_fund.execution.moomoo_paper import MoomooPaperExecution
from ai_henge_fund.paper_trading.engine import PaperTrade
from ai_henge_fund.portfolio.manager import PositionManager


@dataclass(frozen=True)
class MoomooLifecycleResult:
    action: str
    trade: PaperTrade | None
    reason: str
    broker_order_id: str | None = None
    broker_status: str | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None


class MoomooPaperTradeLifecycle:
    """Execute the strategy lifecycle through Moomoo US SIMULATE only.

    The internal PaperTradingEngine is deliberately not used for execution here.
    A position and Telegram trade alert are created only after Moomoo confirms a
    complete fill. A submitted/unfilled order never becomes a local position.
    """

    def __init__(
        self,
        execution: MoomooPaperExecution,
        monitor: MoomooPaperOrderMonitor,
        positions: PositionManager,
        telegram: TelegramNotifier | None = None,
        *,
        fill_timeout_seconds: int = 30,
    ) -> None:
        self.execution = execution
        self.monitor = monitor
        self.positions = positions
        self.telegram = telegram
        self.fill_timeout_seconds = fill_timeout_seconds

    def close(self) -> None:
        self.execution.close()
        self.monitor.close()

    def open(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> MoomooLifecycleResult:
        side = side.upper()
        symbol = symbol.strip().upper()
        if side not in {"BUY", "SELL"}:
            return MoomooLifecycleResult("WAIT", None, "Unsupported opening side")
        if quantity <= 0 or price <= 0:
            return MoomooLifecycleResult("WAIT", None, "Invalid quantity or price")
        if self.positions.get(symbol) is not None:
            return MoomooLifecycleResult("WAIT", None, "Position already open")

        requested_quantity = int(quantity)
        if float(requested_quantity) != float(quantity):
            return MoomooLifecycleResult(
                "WAIT", None, "Moomoo stock paper execution requires whole-share quantity"
            )

        order = self.execution.place_limit(
            symbol=symbol,
            side=side,
            quantity=requested_quantity,
            price=price,
        )
        status = self.monitor.wait_for_terminal(
            order.order_id,
            timeout_seconds=self.fill_timeout_seconds,
        )

        if status.status != FILLED_ALL or status.filled_quantity < requested_quantity:
            return MoomooLifecycleResult(
                "PENDING",
                None,
                "Moomoo paper order submitted but not fully filled",
                broker_order_id=order.order_id,
                broker_status=status.status,
                entry_price=price,
                stop_price=stop_price,
                target_price=target_price,
            )

        fill_price = status.average_price or price
        trade = PaperTrade(
            trade_id=f"moomoo-{order.order_id}",
            symbol=symbol,
            side=side,
            quantity=status.filled_quantity,
            price=fill_price,
            executed_at=datetime.now(timezone.utc),
            status=FILLED_ALL,
            metadata={
                "broker": "moomoo",
                "trading_environment": "SIMULATE",
                "broker_order_id": order.order_id,
                "broker_status": status.status,
                "entry_price": fill_price,
                "stop_price": stop_price,
                "target_price": target_price,
            },
        )
        self.positions.open(symbol, status.filled_quantity, fill_price)
        self._notify(
            trade,
            "MOOMOO_PAPER_FILL",
            stop_price=stop_price,
            target_price=target_price,
        )
        return MoomooLifecycleResult(
            "OPEN",
            trade,
            "Moomoo paper order fully filled",
            broker_order_id=order.order_id,
            broker_status=status.status,
            entry_price=fill_price,
            stop_price=stop_price,
            target_price=target_price,
        )

    def close_position(self, *, symbol: str, price: float) -> MoomooLifecycleResult:
        symbol = symbol.strip().upper()
        position = self.positions.get(symbol)
        if position is None:
            return MoomooLifecycleResult("WAIT", None, "No open position")

        closing_side = "SELL" if position.quantity > 0 else "BUY"
        quantity = abs(position.quantity)
        if float(int(quantity)) != float(quantity):
            return MoomooLifecycleResult(
                "WAIT", None, "Moomoo stock paper execution requires whole-share quantity"
            )

        order = self.execution.place_limit(
            symbol=symbol,
            side=closing_side,
            quantity=int(quantity),
            price=price,
        )
        status = self.monitor.wait_for_terminal(
            order.order_id,
            timeout_seconds=self.fill_timeout_seconds,
        )
        if status.status != FILLED_ALL or status.filled_quantity < quantity:
            return MoomooLifecycleResult(
                "PENDING",
                None,
                "Moomoo paper close order submitted but not fully filled",
                broker_order_id=order.order_id,
                broker_status=status.status,
            )

        fill_price = status.average_price or price
        trade = PaperTrade(
            trade_id=f"moomoo-{order.order_id}",
            symbol=symbol,
            side=closing_side,
            quantity=status.filled_quantity,
            price=fill_price,
            executed_at=datetime.now(timezone.utc),
            status=FILLED_ALL,
            metadata={
                "broker": "moomoo",
                "trading_environment": "SIMULATE",
                "broker_order_id": order.order_id,
                "broker_status": status.status,
            },
        )
        self.positions.close(symbol)
        self._notify(trade, "MOOMOO_PAPER_CLOSE_FILL")
        return MoomooLifecycleResult(
            "CLOSE",
            trade,
            "Moomoo paper close order fully filled",
            broker_order_id=order.order_id,
            broker_status=status.status,
        )

    def _notify(
        self,
        trade: PaperTrade,
        event: str,
        *,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> None:
        if self.telegram is not None:
            self.telegram.send_trade_event(
                symbol=trade.symbol,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                event=event,
                order_id=trade.trade_id,
                stop_price=stop_price,
                target_price=target_price,
            )
