from datetime import date

import pytest

from ai_henge_fund.integrations.tradingagents.adapter import TradingAgentsAdapter


def test_adapter_defers_optional_import(monkeypatch):
    adapter = TradingAgentsAdapter(
        llm_provider="openai",
        deep_think_llm="gpt-4.1",
        quick_think_llm="gpt-4.1-mini",
    )

    class FakeGraph:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def propagate(self, symbol, analysis_date):
            return ({"trace": True}, {"action": "BUY", "confidence": 0.8})

    import tradingagents.default_config as default_config
    import tradingagents.graph.trading_graph as trading_graph

    monkeypatch.setattr(default_config, "DEFAULT_CONFIG", {"existing": "value"})
    monkeypatch.setattr(trading_graph, "TradingAgentsGraph", FakeGraph)

    result = adapter.analyze("NVDA", date(2026, 8, 14))

    assert result.symbol == "NVDA"
    assert result.analysis_date == date(2026, 8, 14)
    assert result.raw_decision["action"] == "BUY"
    assert adapter._graph.kwargs["config"]["llm_provider"] == "openai"


def test_missing_tradingagents_has_actionable_error(monkeypatch):
    adapter = TradingAgentsAdapter(
        llm_provider="openai",
        deep_think_llm="gpt-4.1",
        quick_think_llm="gpt-4.1-mini",
    )

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "tradingagents.default_config":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="TradingAgents is not installed"):
        adapter.analyze("NVDA", date(2026, 8, 14))
