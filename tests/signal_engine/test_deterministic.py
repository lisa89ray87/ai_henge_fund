from ai_hedge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_hedge_fund.signal_engine.deterministic import DeterministicSignalEngine


def snapshot(closes, state="REGULAR"):
    return SignalSnapshot(
        symbol="US.AAPL",
        timestamp=None,
        last_price=closes[-1],
        volume=1000,
        market_state=state,
        candles=tuple({"close": value} for value in closes),
        data_source="test",
        data_quality="LIVE",
    )


def test_upward_sequence_creates_long_candidate():
    signal = DeterministicSignalEngine().evaluate(snapshot([100, 101, 103]))
    assert signal.direction == "LONG"
    assert signal.setup_state == "CANDIDATE"
    assert signal.score >= 4


def test_insufficient_data_fails_closed():
    signal = DeterministicSignalEngine().evaluate(snapshot([100]))
    assert signal.direction == "NEUTRAL"
    assert signal.setup_state == "DATA_INSUFFICIENT"
