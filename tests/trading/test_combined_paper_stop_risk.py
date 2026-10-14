"""Regression tests for combined planned paper stop risk."""
from ai_henge_fund.portfolio.manager import PositionManager
from ai_henge_fund.trading.pipeline import TradingPipeline


def test_combined_stop_risk_long_and_short():
    positions = PositionManager()
    positions.restore("US.AAPL", 10, 100, stop_price=98)
    positions.restore("US.NVDA", -5, 200, stop_price=204)
    pipeline = TradingPipeline(positions=positions)
    assert pipeline._combined_paper_stop_risk() == 40


def test_combined_stop_risk_missing_stop_fails_closed():
    positions = PositionManager()
    positions.restore("US.AAPL", 10, 100)
    pipeline = TradingPipeline(positions=positions)
    assert pipeline._combined_paper_stop_risk() is None


def test_combined_stop_risk_invalid_short_stop_fails_closed():
    positions = PositionManager()
    positions.restore("US.NVDA", -5, 200, stop_price=198)
    pipeline = TradingPipeline(positions=positions)
    assert pipeline._combined_paper_stop_risk() is None
