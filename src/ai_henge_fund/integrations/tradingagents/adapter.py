"""Small, optional adapter around the upstream TradingAgents package.

TradingAgents is deliberately kept behind this boundary so the fund can test
and operate without importing it unless an analysis is requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class TradingAgentsDecision:
    symbol: str
    analysis_date: date
    raw_decision: Any


class TradingAgentsAdapter:
    """Invoke TauricResearch TradingAgents without coupling the core domain to it."""

    def __init__(
        self,
        *,
        llm_provider: str,
        deep_think_llm: str,
        quick_think_llm: str,
        backend_url: str | None = None,
        debug: bool = False,
    ) -> None:
        self._llm_provider = llm_provider
        self._deep_think_llm = deep_think_llm
        self._quick_think_llm = quick_think_llm
        self._backend_url = backend_url
        self._debug = debug
        self._graph: Any | None = None

    def _get_graph(self) -> Any:
        if self._graph is None:
            try:
                from tradingagents.config import TradingAgentsConfig
                from tradingagents.graph.trading_graph import TradingAgentsGraph
            except ImportError as exc:
                raise RuntimeError(
                    "TradingAgents is not installed. Install the project's tradingagents "
                    "optional dependency before running live analysis."
                ) from exc

            config = TradingAgentsConfig(
                llm_provider=self._llm_provider,
                deep_think_llm=self._deep_think_llm,
                quick_think_llm=self._quick_think_llm,
                max_debate_rounds=1,
                max_risk_discuss_rounds=1,
                max_recur_limit=25,
            )

            self._graph = TradingAgentsGraph(
                debug=self._debug,
                config=config,
            )
        return self._graph

    def analyze(self, symbol: str, analysis_date: date) -> TradingAgentsDecision:
        """Run one TradingAgents analysis and return its decision unchanged."""
        _, decision = self._get_graph().propagate(symbol, analysis_date.isoformat())
        return TradingAgentsDecision(
            symbol=symbol,
            analysis_date=analysis_date,
            raw_decision=decision,
        )
