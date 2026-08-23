import pytest

from ai_henge_fund.paper_trading.engine import PaperTradingEngine


def test_paper_trade_is_filled_without_broker_access() -> None:
    trade = PaperTradingEngine().execute(
        symbol="aapl",
        side="buy",
        quantity=10,
        price=309.35,
        metadata={"strategy": "test"},
    )

    assert trade.symbol == "AAPL"
    assert trade.side == "BUY"
    assert trade.quantity == 10
    assert trade.price == 309.35
    assert trade.status == "FILLED"
    assert trade.trade_id.startswith("paper-")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"symbol": "", "side": "BUY", "quantity": 1, "price": 10},
        {"symbol": "AAPL", "side": "HOLD", "quantity": 1, "price": 10},
        {"symbol": "AAPL", "side": "BUY", "quantity": 0, "price": 10},
        {"symbol": "AAPL", "side": "BUY", "quantity": 1, "price": 0},
    ],
)
def test_invalid_paper_trade_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        PaperTradingEngine().execute(**kwargs)
