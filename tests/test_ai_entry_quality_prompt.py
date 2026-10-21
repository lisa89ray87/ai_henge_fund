"""Guard against regression of the shared AI entry-quality prompt."""

from ai_henge_fund.agents.tradingagents_bridge import TradingAgentsRuntime


def test_shared_prompt_requires_evidence_for_weak_volume_and_nearby_support():
    runtime = TradingAgentsRuntime.__new__(TradingAgentsRuntime)
    prompt = runtime._build_lightweight_prompt({
        "symbol": "US.RIVN",
        "market": {"last_price": 12.58, "candles": []},
        "deterministic_signal": {"direction": "SHORT", "score": -7},
    })
    assert "If volume confirmation is weak AND the entry is near opposing support/resistance" in prompt
    assert "confirmed breakdown" in prompt
    assert "Return WAIT when entry quality is uncertain" in prompt


def test_shared_prompt_retains_trade_constraints():
    runtime = TradingAgentsRuntime.__new__(TradingAgentsRuntime)
    prompt = runtime._build_lightweight_prompt({
        "symbol": "US.TTD",
        "market": {"last_price": 12.51, "candles": []},
        "deterministic_signal": {"direction": "SHORT"},
        "trade_constraints": {"minimum_reward_risk": 2.0},
    })
    assert '"minimum_reward_risk":2.0' in prompt
    assert "Paper mode intentionally does not use account-capital limits" in prompt
