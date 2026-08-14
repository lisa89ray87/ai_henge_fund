"""Adapter boundary for the real TradingAgents runtime.

The daily_stock_analyse engine remains the source of truth for imported
signals. TradingAgents is used as a read-only reasoning layer: it analyzes the
symbol/date and returns an independent research decision. This module does not
place orders or connect to a broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class TradingAgentsDecision:
    """Normalized result returned by the reasoning layer."""

    action: str
    confidence: float | None
    rationale: str
    provider: str


class TradingAgentsRuntime(Protocol):
    """Minimal runtime contract so the repository stays provider-agnostic."""

    def analyze(self, request: dict[str, Any]) -> TradingAgentsDecision: ...


class TradingAgentsBridge:
    """Build deterministic requests and delegate analysis to a runtime."""

    def __init__(self, runtime: TradingAgentsRuntime | None = None) -> None:
        self._runtime = runtime

    @property
    def enabled(self) -> bool:
        return self._runtime is not None

    def build_request(self, signal: Any) -> dict[str, Any]:
        """Convert an imported signal into a provider-neutral request."""
        return {
            "symbol": signal.symbol,
            "action": signal.action.value if hasattr(signal.action, "value") else str(signal.action),
            "confidence": float(signal.confidence) if signal.confidence is not None else None,
            "target_price": (
                float(signal.target_price) if signal.target_price is not None else None
            ),
            "reasoning": signal.reasoning,
            "source": signal.source,
            "source_signal_id": signal.source_signal_id,
            "generated_at": signal.generated_at.isoformat() if signal.generated_at else None,
        }

    def analyze(self, signal: Any) -> TradingAgentsDecision:
        """Analyze one signal, requiring an explicitly configured runtime."""
        if self._runtime is None:
            raise RuntimeError(
                "TradingAgents runtime is not configured. Set up the provider adapter "
                "before enabling AI reasoning in production."
            )
        return self._runtime.analyze(self.build_request(signal))


class TradingAgentsGraphRuntime:
    """Production adapter around TauricResearch TradingAgentsGraph.

    TradingAgents receives only a ticker and analysis date. It performs its own
    research/data retrieval and returns an independent decision. No broker or
    order API is called here.
    """

    def __init__(self) -> None:
        try:
            from tradingagents.default_config import DEFAULT_CONFIG
            from tradingagents.graph.trading_graph import TradingAgentsGraph
        except ImportError as exc:
            raise RuntimeError(
                "The tradingagents package is not installed. Install the project "
                "dependencies before running the real reasoning workflow."
            ) from exc

        config = DEFAULT_CONFIG.copy()
        # Keep the verification run bounded while exercising the real graph.
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
        self._graph = TradingAgentsGraph(debug=False, config=config)

    def analyze(self, request: dict[str, Any]) -> TradingAgentsDecision:
        symbol = str(request["symbol"]).strip().upper()
        generated_at = request.get("generated_at")
        if generated_at:
            analysis_date = datetime.fromisoformat(str(generated_at)).date().isoformat()
        else:
            analysis_date = datetime.now().date().isoformat()

        _, decision = self._graph.propagate(symbol, analysis_date)
        if not isinstance(decision, dict):
            raise RuntimeError(
                f"TradingAgents returned an unexpected decision type for {symbol}: "
                f"{type(decision).__name__}"
            )

        action = str(decision.get("action", "hold")).lower()
        confidence_value = decision.get("confidence")
        confidence = float(confidence_value) if confidence_value is not None else None
        rationale = str(decision.get("reasoning") or decision.get("rationale") or "")
        if not rationale:
            raise RuntimeError(f"TradingAgents returned no reasoning for {symbol}.")

        return TradingAgentsDecision(
            action=action,
            confidence=confidence,
            rationale=rationale,
            provider="tradingagents-graph",
        )
