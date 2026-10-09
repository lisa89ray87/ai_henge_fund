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
    assert signal.score >= 6
    assert signal.technical_context["sma20"] > 0
    assert signal.technical_context["rsi14"] is not None


def test_insufficient_data_fails_closed():
    signal = DeterministicSignalEngine().evaluate(snapshot([100]))
    assert signal.direction == "NEUTRAL"
    assert signal.setup_state == "DATA_INSUFFICIENT"


def test_atr_includes_previous_close_gap():
    from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine

    candles = [
        {"high": 101.0, "low": 99.0, "close": 100.0},
        {"high": 111.0, "low": 109.0, "close": 110.0},
    ]
    # Second true range is max(2, 11, 9) = 11, not just high-low = 2.
    assert DeterministicSignalEngine._atr(candles, period=1) == 11.0


def test_atr_without_previous_close_uses_high_low():
    from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine

    assert DeterministicSignalEngine._atr(
        [{"high": 105.0, "low": 100.0, "close": 103.0}], period=14
    ) == 5.0
