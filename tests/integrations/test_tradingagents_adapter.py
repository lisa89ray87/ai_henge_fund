import sys
import types
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

    class FakeTradingAgentsConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    package = types.ModuleType("tradingagents")
    package.__path__ = []
    graph_package = types.ModuleType("tradingagents.graph")
    graph_package.__path__ = []
    config_module = types.ModuleType("tradingagents.config")
    config_module.TradingAgentsConfig = FakeTradingAgentsConfig
    trading_graph_module = types.ModuleType("tradingagents.graph.trading_graph")
    trading_graph_module.TradingAgentsGraph = FakeGraph

    monkeypatch.setitem(sys.modules, "tradingagents", package)
    monkeypatch.setitem(sys.modules, "tradingagents.graph", graph_package)
    monkeypatch.setitem(sys.modules, "tradingagents.config", config_module)
    monkeypatch.setitem(sys.modules, "tradingagents.graph.trading_graph", trading_graph_module)

    result = adapter.analyze("NVDA", date(2026, 8, 14))

    assert result.symbol == "NVDA"
    assert result.analysis_date == date(2026, 8, 14)
    assert result.raw_decision["action"] == "BUY"
    assert adapter._graph.kwargs["config"].llm_provider == "openai"
    assert adapter._graph.kwargs["config"].deep_think_llm == "gpt-4.1"
    assert adapter._graph.kwargs["config"].quick_think_llm == "gpt-4.1-mini"


def test_missing_tradingagents_has_actionable_error(monkeypatch):
    adapter = TradingAgentsAdapter(
        llm_provider="openai",
        deep_think_llm="gpt-4.1",
        quick_think_llm="gpt-4.1-mini",
    )

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "tradingagents.config":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="TradingAgents is not installed"):
        adapter.analyze("NVDA", date(2026, 8, 14))
