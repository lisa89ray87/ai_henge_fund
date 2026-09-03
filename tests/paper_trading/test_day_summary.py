from scripts.send_paper_day_summary import format_trade_block


def test_long_target_trade_uses_requested_telegram_layout():
    block = format_trade_block(
        "LYFT", side="BUY", quantity=500, entry_price=17.11,
        stop_price=None, target_price=17.36,
        exit_quantity=500, exit_price=17.36, pnl=125.0, reason="TARGET",
    )

    assert block == (
        "LYFT\n"
        "  LONG 500\n"
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
