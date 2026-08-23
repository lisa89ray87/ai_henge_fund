from ai_henge_fund.alerts.telegram import TelegramConfig, TelegramNotifier


def test_disabled_telegram_does_not_send(monkeypatch):
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("httpx.post", fail)
    TelegramNotifier(TelegramConfig(bot_token="", chat_id="")).send_trade_event(
        symbol="AAPL", side="BUY", quantity=1, price=309.35
    )
    assert called is False


def test_trade_event_payload(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("httpx.post", fake_post)
    TelegramNotifier(TelegramConfig(bot_token="token", chat_id="123")).send_trade_event(
        symbol="AAPL", side="BUY", quantity=2, price=309.35, event="PAPER_TRADE", order_id="p1"
    )

    assert captured["url"] == "https://api.telegram.org/bottoken/sendMessage"
    assert captured["json"]["chat_id"] == "123"
    assert "AAPL" in captured["json"]["text"]
    assert "PAPER_TRADE" in captured["json"]["text"]
    assert "Order ID: p1" in captured["json"]["text"]
