"""Offline shared reservation gate tests: no network, database or orders."""
import os
from unittest.mock import patch, MagicMock
import pytest
from ai_henge_fund.trading.shared_symbol_reservations import reserve_henge_symbol

def test_disabled_by_default():
    with patch.dict(os.environ, {"SHARED_SYMBOL_RESERVATIONS": "false"}):
        assert reserve_henge_symbol("US.AAPL") is True

def test_enabled_without_db_fails_closed():
    with patch.dict(os.environ, {"SHARED_SYMBOL_RESERVATIONS": "true"}, clear=True):
        with pytest.raises(RuntimeError, match="SHARED_SYMBOL_DATABASE_URL"):
            reserve_henge_symbol("US.AAPL")
