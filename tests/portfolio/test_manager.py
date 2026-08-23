import pytest

from ai_hedge_fund.portfolio.manager import PositionManager


def test_duplicate_position_is_blocked():
    manager = PositionManager()
    manager.open("AAPL", 10, 100)
    assert manager.can_open("AAPL", "BUY") is False
    with pytest.raises(ValueError):
        manager.open("AAPL", 5, 101)


def test_close_removes_position():
    manager = PositionManager()
    manager.open("AAPL", 10, 100)
    position = manager.close("AAPL")
    assert position.quantity == 10
    assert manager.get("AAPL") is None
