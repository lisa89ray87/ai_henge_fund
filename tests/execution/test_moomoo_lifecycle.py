from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ai_hedge_fund.execution.moomoo_order_monitor import MoomooOrderStatus
from ai_hedge_fund.execution.moomoo_paper import MoomooPaperOrder
from ai_hedge_fund.paper_trading.moomoo_lifecycle import MoomooPaperTradeLifecycle
from ai_hedge_fund.portfolio.manager import PositionManager


@dataclass
class FakeExecution:
    order_id: str = "12345"

    def place_limit(self, *, symbol: str, side: str, quantity: int, price: float) -> MoomooPaperOrder:
        return MoomooPaperOrder(
            order_id=self.order_id,
            symbol=symbol,
            side=side,
            quantity=float(quantity),
            price=price,
            status="SUBMITTING",
            raw=None,
        )

    def close(self) -> None:
        pass


@dataclass
class FakeMonitor:
    result: MoomooOrderStatus

    def wait_for_terminal(self, order_id: str, timeout_seconds: int = 30) -> MoomooOrderStatus:
        assert order_id == "12345"
        return self.result

    def close(self) -> None:
        pass


class FakeTelegram:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def send_trade_event(self, **kwargs: object) -> None:
        self.events.append(kwargs)


def test_unfilled_moomoo_order_does_not_create_position_or_alert() -> None:
    positions = PositionManager()
    telegram = FakeTelegram()
    lifecycle = MoomooPaperTradeLifecycle(
        FakeExecution(),
        FakeMonitor(
            MoomooOrderStatus("12345", "SUBMITTED", 1.0, 0.0, 1.0, None)
        ),
        positions,
        telegram,
    )

    result = lifecycle.open(symbol="US.AAPL", side="BUY", quantity=1, price=309.35)

    assert result.action == "PENDING"
    assert positions.get("US.AAPL") is None
    assert telegram.events == []


def test_confirmed_moomoo_fill_creates_position_and_alert() -> None:
    positions = PositionManager()
    telegram = FakeTelegram()
    lifecycle = MoomooPaperTradeLifecycle(
        FakeExecution(),
        FakeMonitor(
            MoomooOrderStatus("12345", "FILLED_ALL", 1.0, 1.0, 0.0, 309.30)
        ),
        positions,
        telegram,
    )

    result = lifecycle.open(symbol="US.AAPL", side="BUY", quantity=1, price=309.35)

    assert result.action == "OPEN"
    position = positions.get("US.AAPL")
    assert position is not None
    assert position.quantity == 1.0
    assert position.average_price == 309.30
    assert len(telegram.events) == 1
    assert telegram.events[0]["event"] == "MOOMOO_PAPER_FILL"
    assert telegram.events[0]["order_id"] == "moomoo-12345"
