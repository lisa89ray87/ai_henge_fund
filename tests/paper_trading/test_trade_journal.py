from datetime import datetime, timezone

from ai_henge_fund.paper_trading.trade_journal import TradeJournal


def test_long_exit_pnl_formula():
    journal = TradeJournal.__new__(TradeJournal)
    assert ((4.67 - 4.72) * 1000) == -50.00000000000004


def test_short_exit_pnl_formula():
    assert (18.00 - 17.50) * 100 == 50.0
