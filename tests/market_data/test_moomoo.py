from datetime import datetime, timezone

import pytest

from ai_henge_fund.market_data.moomoo import MoomooAdapterError, MoomooMarketData


class FakeTransport:
    def get_quote(self, symbol: str):
        assert symbol == "US.NVDA"
        return {
            "last_price": "172.50",
            "bid_price": 172.49,
            "ask_price": 172.51,
            "volume": "12345",
            "update_time": "2026-08-14T14:30:00+00:00",
            "open_price": 170.0,
            "high_price": 173.0,
            "low_price": 169.5,
            "prev_close_price": 171.0,
        }

    def get_candles(self, symbol: str, num: int, interval: str):
        assert symbol == "US.NVDA"
        assert num == 2
        assert interval == "5m"
        return [
            {
                "time_key": "2026-08-14T14:25:00+00:00",
                "open": 171,
                "high": 172,
                "low": 170.5,
                "close": 171.5,
                "volume": 1000,
                "turnover": 171500,
                "last_close": 170.8,
            },
            {
                "time_key": "2026-08-14T14:30:00+00:00",
                "open": 171.5,
                "high": 173,
                "low": 171,
                "close": 172.5,
                "volume": 1234,
                "turnover": 212601,
                "last_close": 171.5,
            },
        ]

    def get_market_state(self, symbol: str):
        assert symbol == "US.NVDA"
        return {"market_state": "AFTERNOON", "stock_name": "NVIDIA"}


def test_disabled_adapter_fails_closed() -> None:
    adapter = MoomooMarketData()
    assert adapter.enabled is False
    with pytest.raises(MoomooAdapterError):
        adapter.get_quote("NVDA")


def test_quote_is_normalized() -> None:
    adapter = MoomooMarketData(FakeTransport(), enabled=True)
    quote = adapter.get_quote(" nvda ")

    assert quote.symbol == "US.NVDA"
    assert quote.last_price == 172.50
    assert quote.bid == 172.49
    assert quote.ask == 172.51
    assert quote.volume == 12345
    assert quote.open_price == 170.0
    assert quote.previous_close == 171.0
    assert quote.timestamp == datetime(2026, 8, 14, 14, 30, tzinfo=timezone.utc)


def test_candles_are_normalized() -> None:
    adapter = MoomooMarketData(FakeTransport(), enabled=True)
    candles = adapter.get_candles("NVDA", num=2, interval="5m")

    assert len(candles) == 2
    assert candles[-1].symbol == "US.NVDA"
    assert candles[-1].open == 171.5
    assert candles[-1].high == 173.0
    assert candles[-1].low == 171.0
    assert candles[-1].close == 172.5
    assert candles[-1].volume == 1234


def test_market_state_is_normalized() -> None:
    adapter = MoomooMarketData(FakeTransport(), enabled=True)
    state = adapter.get_market_state("NVDA")

    assert state.symbol == "US.NVDA"
    assert state.state == "AFTERNOON"
    assert state.stock_name == "NVIDIA"


def test_invalid_candle_count_is_rejected() -> None:
    adapter = MoomooMarketData(FakeTransport(), enabled=True)
    with pytest.raises(ValueError):
        adapter.get_candles("NVDA", num=1001)


def test_empty_symbol_is_rejected() -> None:
    adapter = MoomooMarketData(FakeTransport(), enabled=True)
    with pytest.raises(ValueError):
        adapter.get_quote("   ")
