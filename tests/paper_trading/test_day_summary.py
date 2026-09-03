from ai_henge_fund.portfolio.persistent_trade_state import PersistentTradeStateStore
from scripts.send_paper_day_summary import format_trade_block


def test_persistent_trade_state_store_get_by_symbol_returns_saved_state():
    store = PersistentTradeStateStore()
    store.upsert(
        symbol="US.AAPL",
        side="BUY",
        quantity=10,
        entry_price=100.0,
        stop_price=99.0,
        target_price=110.0,
        broker_order_id="abc-123",
        status="OPEN",
    )

    state = store.get("us.aapl")
    assert state is not None
    assert state.symbol == "US.AAPL"
    assert state.side == "BUY"
    assert state.quantity == 10
    assert state.entry_price == 100.0
    assert state.stop_price == 99.0
    assert state.target_price == 110.0

    store.mark_closed("US.AAPL")
    closed = store.get("US.AAPL")
    assert closed is not None
    assert closed.status == "CLOSED"


def test_long_target_trade_uses_requested_telegram_layout():
    block = format_trade_block(
        "LYFT", side="BUY", quantity=500, entry_price=17.11,
        stop_price=None, target_price=17.36,
        exit_quantity=500, exit_price=17.36, pnl=125.0, reason="TARGET",
    )

    assert block == (
        "LYFT\n"
        "  Entry 500 @ 17.11\n"
        "  Target 17.36\n"
        "  Exit 500 @ 17.36\n"
        "  P/L +125.00\n"
        "  Reason TARGET"
    )


def test_long_stop_trade_formats_negative_pnl():
    block = format_trade_block(
        "LCID", side="BUY", quantity=1000, entry_price=4.72,
        stop_price=4.67, target_price=None,
        exit_quantity=1000, exit_price=4.67, pnl=-45.0, reason="STOP",
    )

    assert "LCID" in block
    assert "Entry 1000 @ 4.72" in block
    assert "Stop 4.67" in block
    assert "Exit 1000 @ 4.67" in block
    assert "P/L -45.00" in block
    assert "Reason STOP" in block
