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

    For BUY/SELL decisions, position size is an explicit AI output. If the
    first analysis omits quantity, the adapter makes a dedicated AI sizing
    request through the same runner before allowing the decision downstream.
    Paper mode does not substitute a quantity from capital/risk settings.
    """

    def __init__(self, runner: TradingAgentsRunner | None = None) -> None:
        self.runner = runner

    @staticmethod
    def _optional_float(result: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = result.get(key)
            if value is None or value == "":
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return None

    def _request_ai_position_size(
        self,
        *,
        snapshot: SignalSnapshot,
        signal: DeterministicSignal,
        decision: str,
        entry_price: float | None,
        stop_price: float | None,
        target_price: float | None,
        base_rationale: str,
    ) -> dict[str, Any]:
        if self.runner is None:
            return {}

        sizing_payload = {
            "task": "POSITION_SIZING_ONLY",
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
            "trade": {
                "decision": decision,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
            },
            "context": {"prior_rationale": base_rationale},
            "capabilities": {
                "market_data": True,
                "orders": False,
                "account_mutation": False,
                "position_sizing": True,
            },
            "requested_output": {
                "quantity": "REQUIRED positive whole-number share quantity",
                "reason": "brief sizing rationale",
            },
            "rules": [
                "Return quantity as a positive whole number of shares.",
                "Do not use or request broker/account mutation capabilities.",
                "Do not use future live capital limits to reduce paper-trading size.",
                "Do not omit quantity when decision is BUY or SELL.",
            ],
        }
        return self.runner.analyze(sizing_payload)

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
                "quantity": "positive whole-number share quantity for BUY/SELL; required for a trade",
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

        quantity = self._optional_float(result, "quantity", "shares", "position_size")
        entry_price = self._optional_float(result, "entry_price", "entry")
        stop_price = self._optional_float(result, "stop_price", "stop")
        target_price = self._optional_float(result, "target_price", "target")

        # A trade must have an AI-controlled size. If the first model response
        # omitted it, explicitly ask the same AI runner for sizing rather than
        # silently substituting a deterministic or capital-derived quantity.
        if decision in {"BUY", "SELL"} and quantity is None:
            sizing_result = self._request_ai_position_size(
                snapshot=snapshot,
                signal=signal,
                decision=decision,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                base_rationale=rationale,
            )
            sizing_quantity = self._optional_float(
                sizing_result, "quantity", "shares", "position_size"
            )
            if sizing_quantity is not None:
                quantity = sizing_quantity
                sizing_reason = str(
                    sizing_result.get("reason", sizing_result.get("rationale", ""))
                ).strip()
                if sizing_reason:
                    rationale = f"{rationale} | AI sizing: {sizing_reason}"
                sizing_provider = str(sizing_result.get("provider", provider))
                provider = f"{provider}+sizing:{sizing_provider}"

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
