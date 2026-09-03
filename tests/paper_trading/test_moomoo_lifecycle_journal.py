from dataclasses import dataclass
from datetime import datetime, timezone

from ai_henge_fund.paper_trading.engine import PaperTrade
from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooPaperTradeLifecycle


@dataclass
class FakeState:
    broker_order_id: str
    side: str
    entry_price: float


class FakeStateStore:
    def __init__(self, state):
        self.state = state
        self.recorded = []

    def get(self, symbol):
        return self.state

    def record_exit(self, **kwargs):
        self.recorded.append(kwargs)


class FakeTradeJournal:
    def __init__(self):
        self.recorded = []

    def record_exit(self, **kwargs):
        self.recorded.append(kwargs)


def _lifecycle(state):
    lifecycle = MoomooPaperTradeLifecycle.__new__(MoomooPaperTradeLifecycle)
    lifecycle._state = FakeStateStore(state)
    lifecycle._trade_journal = FakeTradeJournal()
    lifecycle.telegram = None
    return lifecycle


def test_record_exit_links_to_entry_trade_id_and_journals_pnl_inputs():
    lifecycle = _lifecycle(FakeState("entry-123", "BUY", 4.72))
    trade = PaperTrade(
        trade_id="moomoo-exit-456",
        symbol="US.LCID",
        side="SELL",
        quantity=1000,
        price=4.67,
        executed_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        status="FILLED_ALL",
        metadata={},
    )

    lifecycle._record_exit("US.LCID", trade, 4.67, "exit-456", "STOP")

    journal = lifecycle._trade_journal.recorded
    assert len(journal) == 1
    assert journal[0]["trade_id"] == "moomoo-entry-123"
    assert journal[0]["entry_side"] == "BUY"
    assert journal[0]["entry_price"] == 4.72
    assert journal[0]["quantity"] == 1000
    assert journal[0]["exit_price"] == 4.67
    assert journal[0]["reason"] == "STOP"
    assert journal[0]["broker_exit_order_id"] == "exit-456"

    legacy = lifecycle._state.recorded
    assert len(legacy) == 1
    assert legacy[0]["trade_id"] == "moomoo-entry-123"


def test_record_exit_preserves_distinct_trade_instances_for_reentries():
    lifecycle = _lifecycle(FakeState("entry-001", "BUY", 10.00))
    first = PaperTrade(
        trade_id="moomoo-exit-001", symbol="US.ABC", side="SELL", quantity=10,
        price=11.00, executed_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        status="FILLED_ALL", metadata={},
    )
    lifecycle._record_exit("US.ABC", first, 11.00, "exit-001", "TARGET")
    assert lifecycle._trade_journal.recorded[0]["trade_id"] == "moomoo-entry-001"

    lifecycle._state = FakeStateStore(FakeState("entry-002", "BUY", 12.00))
    second = PaperTrade(
        trade_id="moomoo-exit-002", symbol="US.ABC", side="SELL", quantity=8,
        price=13.00, executed_at=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
        status="FILLED_ALL", metadata={},
    )
    lifecycle._record_exit("US.ABC", second, 13.00, "exit-002", "CLOSE")
    assert lifecycle._trade_journal.recorded[1]["trade_id"] == "moomoo-entry-002"
