from ai_henge_fund.paper_trading.trade_journal import TradeJournal


def test_long_pnl_formula():
    entry = 4.72
    exit_price = 4.67
    quantity = 1000
    assert round((exit_price - entry) * quantity, 2) == -50.00


def test_short_pnl_formula():
    entry = 18.00
    exit_price = 17.50
    quantity = 100
    assert round((entry - exit_price) * quantity, 2) == 50.00


def test_trade_journal_imports():
    assert TradeJournal is not None
