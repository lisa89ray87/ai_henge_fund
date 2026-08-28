"""Adapter boundary for the real TradingAgents runtime.

The daily_stock_analyse engine remains the source of truth for imported
signals. TradingAgents is used as a read-only reasoning layer: it analyzes the
symbol/date and returns an independent research decision. This module does not
place orders or connect to a broker.
"""

from __future__ import annotations

import json
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
    quantity: float | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None


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
    """Production adapter around TauricResearch TradingAgentsGraph."""

    def __init__(self) -> None:
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
        except ImportError as exc:
            raise RuntimeError(
                "The installed TradingAgents package does not expose "
                "tradingagents.graph.trading_graph.TradingAgentsGraph. "
                "Verify that the configured TradingAgents version is installed."
            ) from exc

        self._graph_cls = TradingAgentsGraph
        self._graphs: dict[str, Any] = {}

        if self._has_key("OPENAI_API_KEY"):
            self._primary_provider = "openai"
        elif self._has_gemini_key():
            self._primary_provider = "google_genai"
        else:
            self._primary_provider = None

    @staticmethod
    def _has_key(name: str) -> bool:
        return bool(os.getenv(name, "").strip())

    @classmethod
    def _has_gemini_key(cls) -> bool:
        return cls._has_key("GEMINI_API_KEY") or cls._has_key("GOOGLE_API_KEY")

    @classmethod
    def _prepare_google_key(cls) -> None:
        if not cls._has_key("GOOGLE_API_KEY") and cls._has_key("GEMINI_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    def _build_graph(self, provider: str) -> Any:
        if provider in self._graphs:
            return self._graphs[provider]

        config: dict[str, Any] = {
            "llm_provider": provider,
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "max_recur_limit": 100,
        }

        if provider == "google_genai":
            self._prepare_google_key()
            config["deep_think_llm"] = os.getenv("GEMINI_DEEP_THINK_LLM", "gemini-3.1-flash-lite")
            config["quick_think_llm"] = os.getenv("GEMINI_QUICK_THINK_LLM", "gemini-3.1-flash-lite")
        else:
            config["deep_think_llm"] = os.getenv("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-4.1")
            config["quick_think_llm"] = os.getenv("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-4.1-mini")

        self._graphs[provider] = self._graph_cls(debug=False, config=config)
        return self._graphs[provider]

    @staticmethod
    def _is_provider_failure(exc: Exception) -> bool:
        message = str(exc).lower()
        markers = (
            "429", "rate limit", "rate_limit", "quota", "resource_exhausted",
            "insufficient_quota", "billing", "credit balance", "authentication",
            "unauthorized", "invalid api key", "api key is invalid", "not_found",
            "model is not found", "no longer available", "not supported for generatecontent",
        )
        return any(marker in message for marker in markers)

    @staticmethod
    def _normalize_tradingagents_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized.startswith("US."):
            return normalized[3:]
        return normalized

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _response_text(response: Any) -> str:
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            return "".join(parts).strip()
        return str(content).strip()

    @classmethod
    def _parse_json_object(cls, text: str, symbol: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"AI position sizing returned invalid JSON for {symbol}: {cleaned[:240]}"
            ) from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"AI position sizing returned a non-object response for {symbol}")
        return value

    def _request_ai_position_size(
        self,
        graph: Any,
        request: dict[str, Any],
        action: str,
        entry_price: float | None,
        stop_price: float | None,
        target_price: float | None,
    ) -> int | None:
        """Ask the same configured TradingAgents LLM for the share quantity.

        TradingAgentsGraph's final decision is primarily BUY/SELL/HOLD and does
        not guarantee a sizing field. We therefore make sizing an explicit AI
        sub-decision using the graph's configured quick-thinking model. This is
        still AI-controlled; no capital-budget formula or fixed share fallback
        is used in paper mode.
        """
        symbol = str(request["symbol"]).strip().upper()
        deterministic_direction = str(request.get("deterministic_direction", "NEUTRAL"))
        deterministic_score = request.get("deterministic_score", 0)
        prompt = f"""
You are the position-sizing component of an AI day-trading research system.
Choose the number of whole US stock shares for this PAPER/SIMULATE trade.

The quantity must be an explicit AI decision. Do NOT calculate it from account
capital, maximum deployed capital, daily loss limits, or a fixed one-share
fallback. Those constraints are intentionally disabled in paper simulation.
Use conviction, deterministic signal strength, stop distance, target distance,
and the quality of the setup to choose a sensible whole-share quantity.

Return ONLY valid JSON with exactly:
{{"quantity": <positive integer>, "reason": "brief sizing rationale"}}

Symbol: {symbol}
Action: {action}
Deterministic direction: {deterministic_direction}
Deterministic score: {deterministic_score}
Entry: {entry_price}
Stop: {stop_price}
Target: {target_price}
""".strip()

        response = graph.quick_thinking_llm.invoke(prompt)
        parsed = self._parse_json_object(self._response_text(response), symbol)
        quantity = self._optional_float(parsed.get("quantity"))
        if quantity is None or quantity <= 0 or not quantity.is_integer():
            print(
                f"AI POSITION SIZE INVALID {symbol}: "
                f"quantity={parsed.get('quantity')!r} reason={parsed.get('reason', '')}"
            )
            return None
        print(
            f"AI POSITION SIZE {symbol}: quantity={int(quantity)} "
            f"reason={parsed.get('reason', '')}"
        )
        return int(quantity)

    @classmethod
    def _normalize_decision(
        cls, raw_decision: Any, symbol: str
    ) -> tuple[str, float | None, str, float | None, float | None, float | None, float | None]:
        value = raw_decision
        if isinstance(value, str):
            text = value.strip()
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                action = text.upper()
                if action in {"BUY", "SELL", "HOLD", "WAIT"}:
                    return action, None, f"TradingAgents returned {action} without confidence.", None, None, None, None
                raise RuntimeError(
                    f"TradingAgents returned an unsupported decision string for {symbol}: {text[:200]}"
                )

        if not isinstance(value, dict):
            raise RuntimeError(
                f"TradingAgents returned an unexpected decision type for {symbol}: "
                f"{type(raw_decision).__name__}"
            )

        action = str(value.get("action") or value.get("decision") or value.get("recommendation") or "hold").strip().upper()
        if action in {"HOLD", "WAIT", "NEUTRAL"}:
            action = "HOLD"
        elif action in {"BUY", "LONG"}:
            action = "BUY"
        elif action in {"SELL", "SHORT"}:
            action = "SELL"
        else:
            raise RuntimeError(f"TradingAgents returned unsupported action for {symbol}: {action!r}")

        confidence = cls._optional_float(value.get("confidence"))
        rationale = str(value.get("reasoning") or value.get("rationale") or value.get("analysis") or "").strip()
        if not rationale:
            rationale = f"TradingAgents decision: {action}"

        quantity = cls._optional_float(value.get("quantity", value.get("shares", value.get("position_size"))))
        entry_price = cls._optional_float(value.get("entry_price", value.get("entry")))
        stop_price = cls._optional_float(value.get("stop_price", value.get("stop")))
        target_price = cls._optional_float(value.get("target_price", value.get("target")))

        return action, confidence, rationale, quantity, entry_price, stop_price, target_price

    @staticmethod
    def _deterministic_fallback(request: dict[str, Any], reason: str) -> TradingAgentsDecision:
        direction = str(request.get("deterministic_direction", "NEUTRAL")).upper()
        score = float(request.get("deterministic_score", 0) or 0)
        if direction == "LONG":
            action = "BUY"
        elif direction == "SHORT":
            action = "SELL"
        else:
            action = "HOLD"
        confidence = min(1.0, abs(score) / 8.0)
        return TradingAgentsDecision(
            action=action,
            confidence=confidence,
            rationale=f"AI provider unavailable; deterministic fallback used. {reason}",
            provider="deterministic-fallback",
        )

    def _run(self, provider: str, request: dict[str, Any]) -> TradingAgentsDecision:
        symbol = str(request["symbol"]).strip().upper()
        tradingagents_symbol = self._normalize_tradingagents_symbol(symbol)
        generated_at = request.get("generated_at")
        analysis_date = datetime.fromisoformat(str(generated_at)).date().isoformat() if generated_at else datetime.now().date().isoformat()

        graph = self._build_graph(provider)
        _, raw_decision = graph.propagate(tradingagents_symbol, analysis_date)
        action, confidence, rationale, quantity, entry_price, stop_price, target_price = self._normalize_decision(raw_decision, symbol)

        if action in {"BUY", "SELL"} and quantity is None:
            quantity = self._request_ai_position_size(
                graph,
                request,
                action,
                entry_price,
                stop_price,
                target_price,
            )

        return TradingAgentsDecision(
            action=action,
            confidence=confidence,
            rationale=rationale,
            provider=f"tradingagents-graph:{provider}",
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )

    def analyze(self, request: dict[str, Any]) -> TradingAgentsDecision:
        if self._primary_provider is None:
            print("No AI provider configured; using deterministic fallback.")
            return self._deterministic_fallback(request, "no AI provider configured")

        primary = self._primary_provider
        try:
            return self._run(primary, request)
        except Exception as primary_exc:
            if not self._is_provider_failure(primary_exc):
                raise

            if primary == "openai" and self._has_gemini_key():
                print("OpenAI provider failed with a provider-level error; retrying this analysis with Gemini.")
                try:
                    return self._run("google_genai", request)
                except Exception as gemini_exc:
                    if not self._is_provider_failure(gemini_exc):
                        raise
                    print("Gemini provider also failed with a provider-level error; using deterministic fallback for this analysis.")
                    return self._deterministic_fallback(request, str(gemini_exc))

            print(f"{primary} provider failed with a provider-level error; using deterministic fallback for this analysis.")
            return self._deterministic_fallback(request, str(primary_exc))
