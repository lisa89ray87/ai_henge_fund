"""Unit tests for the daily_stock_analyse database bridge."""

from decimal import Decimal

from ai_henge_fund.database.integrations.daily_stock_analyse import (
    _action,
    _confidence_value,
    _reasoning,
)
from ai_henge_fund.database.models.signal import SignalAction


def test_daily_long_maps_to_buy_and_short_to_sell() -> None:
    assert _action("LONG") is SignalAction.BUY
    assert _action("SHORT") is SignalAction.SELL


def test_daily_confidence_is_normalized_to_decimal() -> None:
    assert _confidence_value("HIGH") == Decimal("0.90")
    assert _confidence_value("MEDIUM") == Decimal("0.60")
    assert _confidence_value("LOW") == Decimal("0.30")
    assert _confidence_value(0.75) == Decimal("0.75")


def test_daily_signal_reasoning_preserves_catalyst_and_regime_context() -> None:
    row = {
        "status": "OPEN",
        "market_regime_label": "RISK_OFF",
        "catalyst_status": "CATALYST_IDENTIFIED",
        "catalyst_category": "EARNINGS",
        "catalyst_direction": "BULLISH",
        "catalyst": "Example catalyst",
        "run_id": "run-1",
    }
    reasoning = _reasoning(row)
    assert "daily_stock_analyse" not in reasoning
    assert "market_regime=RISK_OFF" in reasoning
    assert "catalyst=Example catalyst" in reasoning
    assert "run_id=run-1" in reasoning
