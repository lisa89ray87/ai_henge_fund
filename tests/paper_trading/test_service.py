from ai_henge_fund.paper_trading import PaperTradeService, PaperTradingEngine


class FakeTelegram:
    def __init__(self):
        self.events = []

    def send_trade_event(self, **kwargs):
        self.events.append(kwargs)


def test_paper_trade_emits_one_telegram_event() -> None:
    telegram = FakeTelegram()
    trade = PaperTradeService(PaperTradingEngine(), telegram).execute(
        symbol="AAPL",
        side="BUY",
        quantity=10,
        price=309.35,
    )

    assert len(telegram.events) == 1
    event = telegram.events[0]
    assert event["event"] == "PAPER_TRADE"
    assert event["symbol"] == "AAPL"
    assert event["side"] == "BUY"
    assert event["quantity"] == 10
    assert event["price"] == 309.35
    assert event["order_id"] == trade.trade_id
