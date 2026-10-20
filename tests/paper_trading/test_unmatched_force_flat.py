"""Regression test: unmatched broker positions must never be closed blindly."""
from unittest.mock import Mock

from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooPaperTradeLifecycle


def test_force_flat_unmatched_broker_position_refuses_blind_close(capsys):
    lifecycle = MoomooPaperTradeLifecycle.__new__(MoomooPaperTradeLifecycle)
    lifecycle.execution = Mock()
    lifecycle.execution.list_positions.return_value = [
        {"symbol": "US.XOM", "quantity": 10, "average_price": 100.0}
    ]
    lifecycle.positions = Mock()
    lifecycle.positions.get.return_value = None
    lifecycle._state = Mock()
    lifecycle._state.get.return_value = None
    lifecycle.telegram = None
    lifecycle.close_position = Mock()
    lifecycle._notify_text = Mock()

    assert lifecycle.force_flat_and_verify(max_attempts=1, retry_delay_seconds=0) is False
    lifecycle.close_position.assert_not_called()
    assert "saved state missing" in capsys.readouterr().out
    lifecycle._notify_text.assert_called_once()
