"""Adapter boundary for the real TradingAgents runtime.

The daily_stock_analyse engine remains the source of truth for imported
signals. TradingAgents is used as a read-only reasoning layer: it analyzes the
symbol/date and returns an independent research decision. This module does not
place orders or connect to a broker.
"""

from __future__ import annotations

import json
import os
import threading
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
    quantity_source: str | None = None


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
        if self._runtime is None:
            raise RuntimeError("TradingAgents runtime is not configured.")
        return self._runtime.analyze(self.build_request(signal))


class TradingAgentsGraphRuntime:
    """Production adapter around TauricResearch TradingAgentsGraph.

    For the paper pipeline, TRADINGAGENTS_LIGHTWEIGHT_PAPER_AI=true switches the
    critical AI confirmation step to one direct Gemini call using the Moomoo
    snapshot already collected by the scanner. This avoids TradingAgents' slower
    external research/tool graph while retaining TradingAgents as an optional
    deeper-research path.
    """

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
        self._lightweight_llm: Any | None = None
        self._cancelled_symbols: set[str] = set()
        self._cancel_lock = threading.Lock()
        configured_analysts = os.getenv("TRADINGAGENTS_SELECTED_ANALYSTS", "market,news")
        self._selected_analysts = tuple(
            analyst.strip().lower() for analyst in configured_analysts.split(",") if analyst.strip()
        ) or ("market", "news")

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

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    def cancel(self, symbol: str) -> None:
        normalized = self._normalize_symbol(symbol)
        with self._cancel_lock:
            self._cancelled_symbols.add(normalized)

    def _clear_cancelled(self, symbol: str) -> None:
        normalized = self._normalize_symbol(symbol)
        with self._cancel_lock:
            self._cancelled_symbols.discard(normalized)

    def _is_cancelled(self, symbol: str) -> bool:
        normalized = self._normalize_symbol(symbol)
        with self._cancel_lock:
            return normalized in self._cancelled_symbols

    def _raise_if_cancelled(self, symbol: str) -> None:
        if self._is_cancelled(symbol):
            raise RuntimeError(f"AI analysis cancelled after timeout for {symbol}")

    @staticmethod
    def _normalize_tradingagents_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        return normalized[3:] if normalized.startswith("US.") else normalized

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
            raise RuntimeError(f"AI returned invalid JSON for {symbol}: {cleaned[:300]}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"AI returned a non-object response for {symbol}")
        return value

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
        print(
            f"TRADINGAGENTS GRAPH: provider={provider} analysts={','.join(self._selected_analysts)} "
            f"debate={config['max_debate_rounds']} risk={config['max_risk_discuss_rounds']}"
        )
        self._graphs[provider] = self._graph_cls(
            selected_analysts=self._selected_analysts, debug=False, config=config
        )
        return self._graphs[provider]

    def _build_lightweight_gemini(self) -> Any:
        if self._lightweight_llm is not None:
            return self._lightweight_llm
        if not self._has_gemini_key():
            raise RuntimeError("Gemini API key is not configured")
        self._prepare_google_key()
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("langchain-google-genai is required for lightweight Gemini paper AI") from exc
        model = os.getenv("GEMINI_PAPER_AI_MODEL", "gemini-3.1-flash-lite")
        timeout = float(os.getenv("GEMINI_PAPER_AI_TIMEOUT_SECONDS", "45"))
        print(f"LIGHTWEIGHT GEMINI: model={model} timeout={timeout:.0f}s")
        self._lightweight_llm = ChatGoogleGenerativeAI(
            model=model,
            timeout=timeout,
            max_retries=0,
            temperature=0,
        )
        return self._lightweight_llm

    def _run_lightweight_gemini(self, request: dict[str, Any]) -> TradingAgentsDecision:
        symbol = self._normalize_symbol(str(request["symbol"]))
        self._raise_if_cancelled(symbol)
        market = request.get("market") or {}
        signal = request.get("deterministic_signal") or {}
        candles = list(market.get("candles") or [])[-20:]
        compact_market = {
            "symbol": symbol,
            "last_price": market.get("last_price"),
            "volume": market.get("volume"),
            "market_state": market.get("market_state"),
            "data_quality": market.get("data_quality"),
            "candles": candles,
        }
        prompt = f"""
You are the fast AI confirmation layer for a PAPER/SIMULATE US stock trading system.
Use ONLY the supplied Moomoo market snapshot and deterministic signal. Do not fetch
external data, call tools, or invent unavailable facts. Confirm or reject the
existing directional setup.

Return ONLY one valid JSON object with:
- decision: BUY, SELL, or WAIT
- confidence: number from 0 to 1
- quantity: positive whole number for BUY/SELL, otherwise null
- entry_price: number
- stop_price: number
- target_price: number
- rationale: concise explanation

For BUY require stop < entry < target. For SELL require target < entry < stop.
Paper mode intentionally does not use account-capital limits for sizing. Choose a
reasonable whole-share quantity from setup conviction and signal quality.

DETERMINISTIC SIGNAL:
{json.dumps(signal, separators=(",", ":"), default=str)}

MOOMOO SNAPSHOT:
{json.dumps(compact_market, separators=(",", ":"), default=str)}
""".strip()
        print(f"LIGHTWEIGHT GEMINI REQUEST {symbol}")
        response = self._build_lightweight_gemini().invoke(prompt)
        self._raise_if_cancelled(symbol)
        parsed = self._parse_json_object(self._response_text(response), symbol)
        action = str(parsed.get("decision", "WAIT")).strip().upper()
        if action not in {"BUY", "SELL", "WAIT"}:
            raise RuntimeError(f"Lightweight Gemini returned unsupported decision for {symbol}: {action!r}")
        confidence = self._optional_float(parsed.get("confidence"))
        quantity = self._optional_float(parsed.get("quantity"))
        entry = self._optional_float(parsed.get("entry_price"))
        stop = self._optional_float(parsed.get("stop_price"))
        target = self._optional_float(parsed.get("target_price"))
        if action == "WAIT":
            quantity = None
        elif quantity is None or quantity <= 0 or not quantity.is_integer():
            raise RuntimeError(f"Lightweight Gemini returned invalid quantity for {symbol}: {parsed.get('quantity')!r}")
        if action == "BUY" and not (entry and stop and target and stop < entry < target):
            raise RuntimeError(f"Lightweight Gemini returned invalid BUY levels for {symbol}")
        if action == "SELL" and not (entry and stop and target and target < entry < stop):
            raise RuntimeError(f"Lightweight Gemini returned invalid SELL levels for {symbol}")
        print(f"LIGHTWEIGHT GEMINI RESULT {symbol}: decision={action} confidence={confidence} quantity={quantity}")
        return TradingAgentsDecision(
            action=action,
            confidence=confidence,
            rationale=str(parsed.get("rationale") or "Lightweight Gemini confirmation").strip(),
            provider="google_genai-lightweight",
            quantity=quantity,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            quantity_source="ai-google_genai-lightweight" if quantity is not None else None,
        )

    @staticmethod
    def _is_provider_failure(exc: Exception) -> bool:
        message = str(exc).lower()
        markers = (
            "429", "rate limit", "rate_limit", "quota", "resource_exhausted", "insufficient_quota",
            "billing", "credit balance", "authentication", "unauthorized", "invalid api key",
            "api key is invalid", "not_found", "model is not found", "no longer available",
            "not supported for generatecontent",
        )
        return any(marker in message for marker in markers)

    def _run(self, provider: str, request: dict[str, Any]) -> TradingAgentsDecision:
        symbol = self._normalize_symbol(str(request["symbol"]))
        self._raise_if_cancelled(symbol)
        tradingagents_symbol = self._normalize_tradingagents_symbol(symbol)
        generated_at = request.get("generated_at")
        analysis_date = (
            datetime.fromisoformat(str(generated_at)).date().isoformat()
            if generated_at else datetime.now().date().isoformat()
        )
        graph = self._build_graph(provider)
        _, raw_decision = graph.propagate(tradingagents_symbol, analysis_date)
        self._raise_if_cancelled(symbol)
        value = raw_decision
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = {"action": value}
        if not isinstance(value, dict):
            raise RuntimeError(f"TradingAgents returned unexpected decision for {symbol}")
        action = str(value.get("action") or value.get("decision") or value.get("recommendation") or "HOLD").upper()
        action = {"HOLD": "HOLD", "WAIT": "HOLD", "NEUTRAL": "HOLD", "BUY": "BUY", "LONG": "BUY", "SELL": "SELL", "SHORT": "SELL"}.get(action, "HOLD")
        confidence = self._optional_float(value.get("confidence"))
        rationale = str(value.get("reasoning") or value.get("rationale") or value.get("analysis") or f"TradingAgents decision: {action}").strip()
        quantity = self._optional_float(value.get("quantity", value.get("shares", value.get("position_size"))))
        entry = self._optional_float(value.get("entry_price", value.get("entry")))
        stop = self._optional_float(value.get("stop_price", value.get("stop")))
        target = self._optional_float(value.get("target_price", value.get("target")))
        quantity_source = f"ai-{provider}" if quantity is not None else None
        if action in {"BUY", "SELL"} and quantity is None:
            raise RuntimeError(f"TradingAgents did not provide position size for {symbol}")
        return TradingAgentsDecision(action, confidence, rationale, provider, quantity, entry, stop, target, quantity_source)

    def analyze(self, request: dict[str, Any]) -> TradingAgentsDecision:
        symbol = self._normalize_symbol(str(request["symbol"]))
        self._clear_cancelled(symbol)
        if os.getenv("TRADINGAGENTS_LIGHTWEIGHT_PAPER_AI", "false").strip().lower() in {"1", "true", "yes", "y"}:
            return self._run_lightweight_gemini(request)
        if self._primary_provider is None:
            return self._deterministic_fallback(request, "No configured AI provider")
        try:
            return self._run(self._primary_provider, request)
        except Exception as exc:
            if not self._is_provider_failure(exc):
                raise
            fallback = "google_genai" if self._primary_provider == "openai" and self._has_gemini_key() else "openai" if self._primary_provider == "google_genai" and self._has_key("OPENAI_API_KEY") else None
            if fallback:
                print(f"AI provider failed: provider={self._primary_provider}; symbol={symbol}; reason={exc}; fallback={fallback}")
                return self._run(fallback, request)
            return self._deterministic_fallback(request, str(exc))

    @staticmethod
    def _deterministic_fallback(request: dict[str, Any], reason: str) -> TradingAgentsDecision:
        direction = str(request.get("deterministic_direction", "NEUTRAL")).upper()
        score = float(request.get("deterministic_score", 0) or 0)
        action = "BUY" if direction == "LONG" else "SELL" if direction == "SHORT" else "HOLD"
        confidence = min(1.0, abs(score) / 8.0)
        return TradingAgentsDecision(
            action=action,
            confidence=confidence,
            rationale=f"AI provider unavailable; deterministic fallback used. {reason}",
            provider="deterministic-fallback",
            quantity=1 if action in {"BUY", "SELL"} else None,
            quantity_source="deterministic-fallback" if action in {"BUY", "SELL"} else None,
        )
