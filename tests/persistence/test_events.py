from datetime import datetime, timezone

from ai_henge_fund.persistence.events import InMemoryTradeEventStore, TradeEvent


def test_trade_event_store_preserves_audit_event():
    event = TradeEvent(
        event_type="PAPER_OPEN",
        trade_id="paper-test",
        symbol="US.AAPL",
        side="BUY",
        quantity=10,
        price=100,
        occurred_at=datetime.now(timezone.utc),
        metadata={"strategy": "test", "confidence": 0.9},
    )
    store = InMemoryTradeEventStore()
    store.save(event)

    assert store.all() == [event]
    payload = store.serialize(event)
    assert payload["event_type"] == "PAPER_OPEN"
    assert payload["metadata"]["confidence"] == 0.9
