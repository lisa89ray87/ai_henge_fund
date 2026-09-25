from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine


def snapshot(closes, state="REGULAR"):
    candles = []
    for index, value in enumerate(closes):
        previous = closes[index - 1] if index else value
        candles.append(
            {
                "open": previous,
                "high": value + 0.5,
                "low": value - 0.5,
                "close": value,
                "volume": 1000,
            }
        )
    return SignalSnapshot(
        symbol="US.AAPL",
        timestamp=None,
        last_price=closes[-1],
        volume=1000,
        market_state=state,
        candles=tuple(candles),
        data_source="test",
        data_quality="LIVE",
    )


def test_upward_sequence_creates_long_candidate():
    signal = DeterministicSignalEngine().evaluate(
        snapshot([100, 100.5, 101, 101.5, 102, 102.5, 103, 103.5, 104, 104.5, 105, 105.5, 106, 106.5, 107])
    )
    assert signal.direction == "LONG"
    assert signal.setup_state == "CANDIDATE"
    assert signal.score >= 5
    assert signal.technical_context["sma20"] > 0
    assert signal.technical_context["rsi14"] is not None


def test_insufficient_data_fails_closed():
    signal = DeterministicSignalEngine().evaluate(snapshot([100]))
    assert signal.direction == "NEUTRAL"
    assert signal.setup_state == "DATA_INSUFFICIENT"
