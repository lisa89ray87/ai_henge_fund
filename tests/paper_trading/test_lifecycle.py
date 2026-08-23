from ai_henge_fund.paper_trading.engine import PaperTradingEngine
from ai_henge_fund.paper_trading.lifecycle import PaperTradeLifecycle
from ai_henge_fund.portfolio.manager import PositionManager


class FakeTelegram:
    def __init__(self):
        self.events = []

    def send_trade_event(self, **kwargs):
        self.events.append(kwargs)


def test_lifecycle_emits_open_once_and_blocks_duplicate():
    telegram = FakeTelegram()
    lifecycle = PaperTradeLifecycle(PaperTradingEngine(), PositionManager(), telegram)

    first = lifecycle.open(symbol="AAPL", side="BUY", quantity=10, price=100)
    second = lifecycle.open(symbol="AAPL", side="BUY", quantity=10, price=101)

    assert first.action == "OPEN"
    assert second.action == "WAIT"
    assert len(telegram.events) == 1
    assert telegram.events[0]["event"] == "PAPER_OPEN"


def test_lifecycle_closes_position_and_emits_close():
    telegram = FakeTelegram()
    lifecycle = PaperTradeLifecycle(PaperTradingEngine(), PositionManager(), telegram)

    lifecycle.open(symbol="AAPL", side="BUY", quantity=10, price=100)
    result = lifecycle.close(symbol="AAPL", price=105)

    assert result.action == "CLOSE"
    assert result.trade.side == "SELL"
    assert len(telegram.events) == 2
    assert telegram.events[1]["event"] == "PAPER_CLOSE"
