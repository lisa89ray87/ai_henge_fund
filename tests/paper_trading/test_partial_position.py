from ai_henge_fund.portfolio.manager import PositionManager


def test_reduce_long_position_preserves_protection():
    positions = PositionManager()
    positions.open_signed("US.TEST", 100, 10.0, stop_price=9.5, target_price=11.0)

    remaining = positions.reduce("US.TEST", 40)

    assert remaining is not None
    assert remaining.quantity == 60
    assert remaining.average_price == 10.0
    assert remaining.stop_price == 9.5
    assert remaining.target_price == 11.0


def test_reduce_short_position_preserves_direction():
    positions = PositionManager()
    positions.open_signed("US.TEST", -100, 20.0, stop_price=21.0, target_price=18.0)

    remaining = positions.reduce("US.TEST", 25)

    assert remaining is not None
    assert remaining.quantity == -75
    assert remaining.average_price == 20.0
    assert remaining.stop_price == 21.0
    assert remaining.target_price == 18.0


def test_reduce_full_position_closes_it():
    positions = PositionManager()
    positions.open_signed("US.TEST", 50, 10.0)

    remaining = positions.reduce("US.TEST", 50)

    assert remaining is None
    assert positions.get("US.TEST") is None
