from ai_hedge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_hedge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_hedge_fund.tradingagents.adapter import TradingAgentsAdapter


def make_snapshot():
    return SignalSnapshot(
        symbol="US.AAPL",
        timestamp=None,
        last_price=103,
        volume=1000,
        market_state="REGULAR",
        candles=tuple({"close": x} for x in [100, 101, 103]),
        data_source="test",
        data_quality="LIVE",
    )


def test_adapter_falls_back_without_runner():
    snapshot = make_snapshot()
    signal = DeterministicSignalEngine().evaluate(snapshot)
    decision = TradingAgentsAdapter().analyze(snapshot, signal)

    assert decision.decision == "BUY"
    assert decision.provider == "deterministic-fallback"
    assert decision.confidence == 0.0


def test_adapter_restricts_invalid_runner_decision():
    class Runner:
        def analyze(self, payload):
            assert payload["capabilities"]["orders"] is False
            return {"decision": "YOLO", "confidence": 2, "rationale": "bad"}

    snapshot = make_snapshot()
    signal = DeterministicSignalEngine().evaluate(snapshot)
    decision = TradingAgentsAdapter(Runner()).analyze(snapshot, signal)

    assert decision.decision == "WAIT"
    assert decision.confidence == 1.0
