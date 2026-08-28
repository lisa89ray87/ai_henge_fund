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
    quantity: float | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None


class TradingAgentsRunner(Protocol):
    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class TradingAgentsAdapter:
    """Safe boundary between deterministic signals and TradingAgents.

    TradingAgents receives structured evidence and can only return an analysis
    decision. It is not given broker/order capabilities by this adapter.

    When the runtime supplies position-sizing fields, those fields are carried
    through for paper execution. Mechanical validation remains downstream.
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
            "deterministic_direction": signal.direction,
            "deterministic_score": signal.score,
            "capabilities": {
                "market_data": True,
                "orders": False,
                "account_mutation": False,
                "position_sizing": True,
            },
            "requested_output": {
                "decision": "BUY|SELL|WAIT",
                "confidence": "0..1",
                "quantity": "positive share quantity for BUY/SELL; required for a trade",
                "entry_price": "planned entry price",
                "stop_price": "protective stop price",
                "target_price": "profit target price",
                "rationale": "brief explanation",
            },
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

        def _optional_float(key: str) -> float | None:
            value = result.get(key)
            if value is None or value == "":
                return None
            return float(value)

        quantity = _optional_float("quantity")
        entry_price = _optional_float("entry_price")
        stop_price = _optional_float("stop_price")
        target_price = _optional_float("target_price")

        return AITradeDecision(
            snapshot.symbol,
            decision,
            confidence,
            rationale,
            provider,
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )
