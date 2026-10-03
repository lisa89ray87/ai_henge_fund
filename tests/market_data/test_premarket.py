from types import SimpleNamespace

from ai_henge_fund.market_data.premarket import build_premarket_candidates, extract_premarket


def _quote(symbol: str, change: float, volume: int):
    return SimpleNamespace(
        symbol=symbol,
        previous_close=100.0,
        raw={
            "pre_price": 100.0 + change,
            "pre_change_rate": change,
            "pre_volume": volume,
            "pre_high_price": 101.0 + change,
            "pre_low_price": 99.0 + change,
        },
    )


def test_extract_premarket_uses_moomoo_pre_fields():
    item = extract_premarket(_quote("US.AAPL", 2.5, 12000))

    assert item.symbol == "US.AAPL"
    assert item.premarket_price == 102.5
    assert item.premarket_change_pct == 2.5
    assert item.premarket_volume == 12000


def test_build_premarket_candidates_prioritizes_largest_move():
    quotes = [
        _quote("US.AAPL", 0.5, 1000),
        _quote("US.NVDA", -3.0, 2000),
        _quote("US.META", 1.5, 3000),
    ]

    candidates = build_premarket_candidates(quotes, limit=2)

    assert [item.symbol for item in candidates] == ["US.NVDA", "US.META"]
