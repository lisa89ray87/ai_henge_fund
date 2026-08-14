from datetime import datetime, timezone

import pytest

from ai_henge_fund.market_data.moomoo import MoomooAdapterError, MoomooMarketData


class FakeTransport:
    def get_quote(self, symbol: str):
        assert symbol == "NVDA"
        return {
            "lastPrice": "172.50",
            "bidPrice": 172.49,
            "askPrice": 172.51,
            "volume": "12345",
            "timestamp": "2026-08-14T14:30:00Z",
        }


def test_disabled_adapter_fails_closed() -> None:
    adapter = MoomooMarketData()
    assert adapter.enabled is False
    with pytest.raises(MoomooAdapterError):
        adapter.get_quote("NVDA")


def test_quote_is_normalized_without_order_capability() -> None:
    adapter = MoomooMarketData(FakeTransport(), enabled=True)
    quote = adapter.get_quote(" nvda ")

    assert quote.symbol == "NVDA"
    assert quote.last_price == 172.50
    assert quote.bid == 172.49
    assert quote.ask == 172.51
    assert quote.volume == 12345
    assert quote.timestamp == datetime(2026, 8, 14, 14, 30, tzinfo=timezone.utc)


def test_empty_symbol_is_rejected() -> None:
    adapter = MoomooMarketData(FakeTransport(), enabled=True)
    with pytest.raises(ValueError):
        adapter.get_quote("   ")
