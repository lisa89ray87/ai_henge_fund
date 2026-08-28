from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_henge_fund.tradingagents.adapter import TradingAgentsAdapter


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


def test_adapter_requests_ai_sizing_when_trade_has_no_quantity():
    class Runner:
        def __init__(self):
            self.calls = []

        def analyze(self, payload):
            self.calls.append(payload)
            if payload.get("task") == "POSITION_SIZING_ONLY":
                return {"quantity": 7, "reason": "strong setup", "provider": "test-sizer"}
            return {
                "decision": "BUY",
                "confidence": 0.9,
                "entry_price": 103,
                "stop_price": 101,
                "target_price": 107,
                "rationale": "test trade",
                "provider": "test-model",
            }

    runner = Runner()
    snapshot = make_snapshot()
    signal = DeterministicSignalEngine().evaluate(snapshot)
    decision = TradingAgentsAdapter(runner).analyze(snapshot, signal)

    assert decision.decision == "BUY"
    assert decision.quantity == 7
    assert "sizing:test-sizer" in decision.provider
    assert len(runner.calls) == 2
    assert runner.calls[1]["task"] == "POSITION_SIZING_ONLY"
    assert runner.calls[1]["requested_output"]["quantity"].startswith("REQUIRED")
