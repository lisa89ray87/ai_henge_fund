import json
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_henge_fund.agents.tradingagents_bridge import TradingAgentsGraphRuntime
from ai_henge_fund.config.settings import get_settings
from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.risk.gate import RiskGate
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_henge_fund.trading.pipeline import TradingPipeline
from ai_henge_fund.tradingagents.adapter import AITradeDecision, TradingAgentsAdapter


def setup(direction="LONG", regime="NEUTRAL", price=894.14):
    snapshot = SignalSnapshot(
        symbol="US.GS", timestamp=None, last_price=price, volume=1000,
        market_state="REGULAR", data_source="test", data_quality="LIVE",
        candles=tuple({"close": price, "high": 895.0, "low": 890.95} for _ in range(20)),
        metadata={"market_regime": regime},
    )
    signal = replace(DeterministicSignalEngine().evaluate(snapshot),
                     direction=direction, score=9 if direction == "LONG" else -9,
                     setup_state="CANDIDATE")
    return snapshot, signal


@pytest.mark.parametrize("direction,stop,target,expected_boundary", [
    ("LONG", 890.94, 900.55, 890.95),
    ("SHORT", 895.01, 892.39, 895.0),
])
def test_ai_receives_boundary_enforced_by_gate(direction, stop, target, expected_boundary):
    snapshot, signal = setup(direction)
    gate = RiskGate()
    payload = TradingAgentsAdapter()._build_payload(snapshot, signal)
    constraints = payload["trade_constraints"]
    assert constraints["structural_stop_boundary"] == expected_boundary
    action = "BUY" if direction == "LONG" else "SELL"
    valid = AITradeDecision(snapshot.symbol, action, .9, "test", "test",
                           quantity=2, entry_price=894.14, stop_price=stop, target_price=target)
    assert gate.evaluate(snapshot, signal, valid).action == action
    inside = expected_boundary + .01 if action == "BUY" else expected_boundary - .01
    rejected = gate.evaluate(snapshot, signal, replace(valid, stop_price=inside))
    assert "STRUCTURAL_STOP_REJECT" in rejected.checks


@pytest.mark.parametrize("direction,regime,expected", [
    ("LONG", "RISK_ON", 1.75), ("SHORT", "RISK_OFF", 1.75),
    ("LONG", "NEUTRAL", 2.0), ("LONG", "UNKNOWN", 2.0),
])
def test_aggressive_ai_constraints_match_effective_rr(monkeypatch, direction, regime, expected):
    monkeypatch.setenv("AI_HEDGE_FUND_RISK_PROFILE", "aggressive_paper")
    get_settings.cache_clear()
    snapshot, signal = setup(direction, regime)
    gate = RiskGate()
    pipeline = TradingPipeline(risk_gate=gate, ai_adapter=TradingAgentsAdapter())
    constraints = pipeline.ai_adapter._build_payload(snapshot, signal)["trade_constraints"]
    assert constraints["minimum_reward_risk"] == expected
    assert constraints["atr_buffer_multiple"] == .05


def test_pipeline_sends_custom_gate_constraints_and_rechecks_revision():
    snapshot, signal = setup()
    calls = []

    class Runner:
        def analyze(self, payload):
            calls.append(payload)
            assert payload["trade_constraints"]["minimum_reward_risk"] == 2.5
            assert payload["trade_constraints"]["structural_stop_boundary"] == 890.95
            stop = 891.98 if len(calls) == 1 else 890.94
            return dict(decision="BUY", confidence=.85, quantity=2,
                        entry_price=894.14, stop_price=stop, target_price=902.2)

    pipeline = TradingPipeline(signal_engine=SimpleNamespace(evaluate=lambda _: signal),
                               risk_gate=RiskGate(reward_risk_multiple=2.5),
                               ai_adapter=TradingAgentsAdapter(Runner()))
    result = pipeline.analyze(snapshot)
    assert len(calls) == 2
    assert calls[1]["task"] == "RISK_AWARE_SETUP_REVISION"
    assert calls[1]["previous_trade_levels"]["stop_price"] == 891.98
    assert result.risk.action == "BUY"
    assert "AI_RISK_REVISION" in result.risk.checks


def test_lightweight_prompt_preserves_numeric_constraints_and_revision():
    runtime = object.__new__(TradingAgentsGraphRuntime)
    runtime._cancelled_symbols = set()
    runtime._cancel_lock = threading.Lock()
    prompts = []

    class LLM:
        def invoke(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(content=json.dumps({"decision": "WAIT", "confidence": .5}))

    runtime._lightweight_llm = LLM()
    snapshot, signal = setup()
    adapter = TradingAgentsAdapter()
    request = adapter._build_payload(snapshot, signal, risk_feedback="stop rejected at 890.95",
                                     previous_levels=(894.14, 891.98, 900.0))
    runtime._run_lightweight_gemini(request)
    assert len(prompts) == 1
    assert '"structural_stop_boundary":890.95' in prompts[0]
    assert '"minimum_reward_risk":2.0' in prompts[0]
    assert "RISK_AWARE_SETUP_REVISION" in prompts[0]
    assert "stop rejected at 890.95" in prompts[0]
    assert '"stop_price":891.98' in prompts[0]
    assert "return WAIT if it is unrealistic" in prompts[0]


@pytest.mark.parametrize("direction,price,expected", [
    ("LONG", 890.96, 890.555), ("SHORT", 894.99, 895.395),
])
def test_atr_boundary_recomputes_for_entry(direction, price, expected):
    snapshot, signal = setup(direction, price=price)
    gate = RiskGate()
    constraints = gate.trade_constraints(snapshot, signal)
    assert constraints["structural_stop_boundary"] == pytest.approx(expected)
    shifted = price - 1 if direction == "LONG" else price + 1
    boundary = gate.structural_stop_boundary(snapshot, constraints["direction"], shifted)
    assert boundary == pytest.approx(expected - 1 if direction == "LONG" else expected + 1)
