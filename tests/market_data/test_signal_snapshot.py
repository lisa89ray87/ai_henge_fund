from datetime import datetime, timezone

from ai_henge_fund.market_data.signal_snapshot import build_signal_snapshot


class Quote:
    timestamp = datetime(2026, 8, 23, 8, 54, tzinfo=timezone.utc)
    last_price = 309.35
    volume = 46876815


class MarketState:
    state = "AFTER_HOURS_END"


class Candle:
    def to_dict(self):
        return {"close": 309.35, "volume": 6517668}


def test_build_snapshot_preserves_data_quality_and_source() -> None:
    snapshot = build_signal_snapshot(
        symbol=" us.aapl ",
        quote=Quote(),
        market_state=MarketState(),
        candles=[Candle()],
    )

    assert snapshot.symbol == "US.AAPL"
    assert snapshot.last_price == 309.35
    assert snapshot.volume == 46876815
    assert snapshot.market_state == "AFTER_HOURS_END"
    assert snapshot.data_source == "moomoo_opend"
    assert snapshot.data_quality == "LIVE"
    assert snapshot.is_usable is True
    assert snapshot.to_dict()["candles"][0]["close"] == 309.35
