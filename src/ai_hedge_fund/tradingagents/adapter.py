from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ai_hedge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_hedge_fund.signal_engine.deterministic import DeterministicSignal


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
            "capabilities": {"market_data": True, "orders": False, "account_mutation": False},
        }

        if self.runner is None:
            return AITradeDecision(
                snapshot.symbol,
                signal.direction if signal.direction != "NEUTRAL" else "WAIT",
                0.0,
                "TradingAgents runner not configured; deterministic signal only",
                "deterministic-fallback",
            )

        result = self.runner.analyze(payload)
        decision = str(result.get("decision", "WAIT")).upper()
        if decision not in {"BUY", "SELL", "WAIT"}:
            decision = "WAIT"
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
        rationale = str(result.get("rationale", "No rationale returned"))
        return AITradeDecision(snapshot.symbol, decision, confidence, rationale, "tradingagents")
