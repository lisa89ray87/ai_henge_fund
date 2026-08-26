"""Adapter boundary for the real TradingAgents runtime.

The daily_stock_analyse engine remains the source of truth for imported
signals. TradingAgents is used as a read-only reasoning layer: it analyzes the
symbol/date and returns an independent research decision. This module does not
place orders or connect to a broker.

LLM provider behavior is deliberately resilient:
- OpenAI is preferred when its key is available.
- Gemini/Google is used automatically when OpenAI is unavailable.
- If an OpenAI call fails with a quota/rate-limit/authentication style error,
  the same analysis is retried once with Gemini when its key is available.
"""

from __future__ import annotations

import os
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
            "target_price": float(signal.target_price) if signal.target_price is not None else None,
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

    We intentionally do not import ``DEFAULT_CONFIG`` here. Some packaged
    TradingAgents builds expose the graph but do not expose that convenience
    constant at the package root. The graph accepts a normal configuration
    dictionary, so using an explicit minimal configuration keeps this adapter
    compatible with the installed package while still allowing environment
    overrides.
    """

    def __init__(self) -> None:
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
        except ImportError as exc:
            raise RuntimeError(
                "The installed TradingAgents package does not expose "
                "tradingagents.graph.trading_graph.TradingAgentsGraph. "
                "Verify that tradingagents>=0.3.1,<0.4.0 is installed."
            ) from exc

        self._graph_cls = TradingAgentsGraph
        self._graphs: dict[str, Any] = {}

        if self._has_key("OPENAI_API_KEY"):
            self._primary_provider = "openai"
        elif self._has_gemini_key():
            self._primary_provider = "google_genai"
        else:
            raise RuntimeError(
                "No AI provider is configured. Set OPENAI_API_KEY and/or GEMINI_API_KEY."
            )

    @staticmethod
    def _has_key(name: str) -> bool:
        return bool(os.getenv(name, "").strip())

    @classmethod
    def _has_gemini_key(cls) -> bool:
        return cls._has_key("GEMINI_API_KEY") or cls._has_key("GOOGLE_API_KEY")

    @classmethod
    def _prepare_google_key(cls) -> None:
        """Map our user-facing GEMINI_API_KEY secret to TradingAgents' GOOGLE_API_KEY."""
        if not cls._has_key("GOOGLE_API_KEY") and cls._has_key("GEMINI_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    def _build_graph(self, provider: str) -> Any:
        if provider in self._graphs:
            return self._graphs[provider]

        config: dict[str, Any] = {
            "llm_provider": provider,
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "max_recur_limit": 25,
        }

        if provider == "google_genai":
            self._prepare_google_key()
            config["deep_think_llm"] = os.getenv(
                "GEMINI_DEEP_THINK_LLM", "gemini-3.6-flash"
            )
            config["quick_think_llm"] = os.getenv(
                "GEMINI_QUICK_THINK_LLM", "gemini-3.6-flash"
            )
        else:
            config["deep_think_llm"] = os.getenv(
                "TRADINGAGENTS_DEEP_THINK_LLM", "gpt-4.1"
            )
            config["quick_think_llm"] = os.getenv(
                "TRADINGAGENTS_QUICK_THINK_LLM", "gpt-4.1-mini"
            )

        self._graphs[provider] = self._graph_cls(debug=False, config=config)
        return self._graphs[provider]

    @staticmethod
    def _is_provider_failure(exc: Exception) -> bool:
        """Return True only for failures where changing LLM providers is sensible."""
        message = str(exc).lower()
        markers = (
            "429",
            "rate limit",
            "rate_limit",
            "quota",
            "insufficient_quota",
            "billing",
            "credit balance",
            "authentication",
            "unauthorized",
            "invalid api key",
            "api key is invalid",
        )
        return any(marker in message for marker in markers)

    def _run(self, provider: str, request: dict[str, Any]) -> TradingAgentsDecision:
        symbol = str(request["symbol"]).strip().upper()
        generated_at = request.get("generated_at")
        if generated_at:
            analysis_date = datetime.fromisoformat(str(generated_at)).date().isoformat()
        else:
            analysis_date = datetime.now().date().isoformat()

        _, decision = self._build_graph(provider).propagate(symbol, analysis_date)
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
            provider=f"tradingagents-graph:{provider}",
        )

    def analyze(self, request: dict[str, Any]) -> TradingAgentsDecision:
        """Run the primary provider and fall back to Gemini when appropriate."""
        primary = self._primary_provider
        try:
            return self._run(primary, request)
        except Exception as primary_exc:
            if primary != "openai" or not self._has_gemini_key():
                raise
            if not self._is_provider_failure(primary_exc):
                raise

            print(
                "OpenAI provider failed with a provider-level error; "
                "retrying this analysis with Gemini."
            )
            return self._run("google_genai", request)
