from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.signal_engine.deterministic import DeterministicSignal


@dataclass(frozen=True)
class AITradeDecision:
    symbol: str
    decision: str
    confidence: float
    rationale: str
    provider: str


class TradingAgentsRunner(Protocol):
    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class TradingAgentsAdapter:
    """Safe boundary between deterministic signals and TradingAgents.

    TradingAgents receives structured evidence and can only return an analysis
    decision. It is not given broker/order capabilities by this adapter.
    """

    def __init__(self, runner: TradingAgentsRunner | None = None) -> None:
        self.runner = runner

    def analyze(self, snapshot: SignalSnapshot, signal: DeterministicSignal) -> AITradeDecision:
        if not snapshot.is_usable:
            return AITradeDecision(snapshot.symbol, "WAIT", 0.0, "Market snapshot is not usable", "none")

        payload = {
            "symbol": snapshot.symbol,
            "market": snapshot.to_dict(),
            "deterministic_signal": {
                "direction": signal.direction,
                "score": signal.score,
                "trend": signal.trend,
                "momentum": signal.momentum,
                "price_action": signal.price_action,
                "volume_confirmation": signal.volume_confirmation,
                "market_alignment": signal.market_alignment,
                "setup_state": signal.setup_state,
                "reasons": list(signal.reasons),
            },
            # Explicit fallback inputs let the runtime continue paper-testing
            # when OpenAI/Gemini quotas or provider access are temporarily down.
            "deterministic_direction": signal.direction,
            "deterministic_score": signal.score,
            "capabilities": {"market_data": True, "orders": False, "account_mutation": False},
        }

        if self.runner is None:
            fallback_decision = {
                "LONG": "BUY",
                "SHORT": "SELL",
                "NEUTRAL": "WAIT",
            }.get(signal.direction, "WAIT")
            fallback_confidence = min(1.0, abs(signal.score) / 8.0)

            return AITradeDecision(
                snapshot.symbol,
                fallback_decision,
                fallback_confidence,
                "TradingAgents runner not configured; deterministic fallback used",
                "deterministic-fallback",
            )

        result = self.runner.analyze(payload)
        decision = str(result.get("decision", "WAIT")).upper()
        if decision not in {"BUY", "SELL", "WAIT"}:
            decision = "WAIT"
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
        rationale = str(result.get("rationale", "No rationale returned"))
        provider = str(result.get("provider", "tradingagents"))
        return AITradeDecision(snapshot.symbol, decision, confidence, rationale, provider)
