from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.risk.gate import RiskGate
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_henge_fund.tradingagents.adapter import AITradeDecision


def make_snapshot():
    return SignalSnapshot(
        symbol="US.AAPL", timestamp=None, last_price=100, volume=1000,
        market_state="REGULAR", candles=tuple({"close": x} for x in [100, 101, 103]),
        data_source="test", data_quality="LIVE",
    )


def test_risk_gate_accepts_confirmed_candidate():
    snapshot = make_snapshot()
    signal = DeterministicSignalEngine().evaluate(snapshot)
    ai = AITradeDecision("US.AAPL", "BUY", 0.85, "confirmed", "test")
    result = RiskGate().evaluate(snapshot, signal, ai)
    assert result.action == "BUY"
    assert result.quantity == 100
    assert "AI_CONFIDENCE" in result.checks


def test_risk_gate_fails_on_low_ai_confidence():
    snapshot = make_snapshot()
    signal = DeterministicSignalEngine().evaluate(snapshot)
    ai = AITradeDecision("US.AAPL", "BUY", 0.50, "weak", "test")
    result = RiskGate().evaluate(snapshot, signal, ai)
    assert result.action == "WAIT"
    assert result.quantity == 0


def test_risk_gate_rejects_closed_market_state():
    snapshot = SignalSnapshot(
        symbol="US.AAPL", timestamp=None, last_price=100, volume=1000,
        market_state="AFTER_HOURS_END", candles=tuple({"close": x} for x in [100, 101, 103]),
        data_source="test", data_quality="LIVE",
    )
    signal = DeterministicSignalEngine().evaluate(snapshot)
    ai = AITradeDecision("US.AAPL", "BUY", 0.90, "confirmed", "test")
    result = RiskGate().evaluate(snapshot, signal, ai)
    assert result.action == "WAIT"
