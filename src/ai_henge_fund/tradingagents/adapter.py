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
    quantity_source: str | None = None


class TradingAgentsRunner(Protocol):
    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class TradingAgentsAdapter:
    """Safe boundary between deterministic signals and TradingAgents."""

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

    def _build_payload(
        self,
        snapshot: SignalSnapshot,
        signal: DeterministicSignal,
        *,
        risk_feedback: str | None = None,
        previous_levels: tuple[float, float, float] | None = None,
    ) -> dict[str, Any]:
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
                "technical_context": dict(signal.technical_context or {}),
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
                "stop_price": "protective stop price based on recent structure and ATR, not an arbitrary fixed distance",
                "target_price": "profit target price with at least the configured reward/risk multiple",
                "rationale": "brief explanation including why the setup is valid or why WAIT is safer",
            },
            "strategy_rules": {
                "market_regime": "RISK_ON, NEUTRAL, RISK_OFF, or UNKNOWN from market.metadata",
                "risk_off": "do not open new LONG positions unless the supplied regime explicitly permits it; prefer WAIT when alignment is weak",
                "risk_on": "do not open new SHORT positions unless the supplied regime explicitly permits it; prefer WAIT when alignment is weak",
                "no_trade": "WAIT is a valid and preferred decision when setup quality, regime alignment, entry location, or risk/reward is insufficient",
                "stop_method": "place the stop beyond recent swing structure with a small ATR buffer",
                "position_sizing": "size from setup conviction and distance to structural stop; never increase size merely because the stock price is low",
            },
        }
        if risk_feedback:
            payload["task"] = "RISK_AWARE_SETUP_REVISION"
            payload["risk_feedback"] = risk_feedback
            if previous_levels is not None:
                entry, stop, target = previous_levels
                payload["previous_trade_levels"] = {
                    "entry_price": entry,
                    "stop_price": stop,
                    "target_price": target,
                }
            payload["strategy_rules"]["revision_rule"] = (
                "Revise the setup only if the thesis remains valid. Do not weaken or bypass "
                "structural-stop or minimum reward/risk protections. If no valid setup can "
                "satisfy the supplied constraints, return WAIT."
            )
        return payload

    def _decision_from_result(self, snapshot: SignalSnapshot, result: dict[str, Any]) -> AITradeDecision:
        decision = str(result.get("decision", "WAIT")).upper()
        if decision not in {"BUY", "SELL", "WAIT"}:
            decision = "WAIT"
        try:
            confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        rationale = str(result.get("rationale", "No rationale returned"))
        provider = str(result.get("provider", "tradingagents"))
        quantity = self._optional_float(result, "quantity", "shares", "position_size")
        entry_price = self._optional_float(result, "entry_price", "entry")
        stop_price = self._optional_float(result, "stop_price", "stop")
        target_price = self._optional_float(result, "target_price", "target")
        quantity_source = str(result.get("quantity_source", "")).strip() or None
        return AITradeDecision(
            snapshot.symbol, decision, confidence, rationale, provider,
            quantity=quantity, entry_price=entry_price, stop_price=stop_price,
            target_price=target_price, quantity_source=quantity_source,
        )

    def analyze(self, snapshot: SignalSnapshot, signal: DeterministicSignal) -> AITradeDecision:
        if not snapshot.is_usable:
            return AITradeDecision(snapshot.symbol, "WAIT", 0.0, "Market snapshot is not usable", "none")

        payload = self._build_payload(snapshot, signal)

        if self.runner is None:
            fallback_decision = {"LONG": "BUY", "SHORT": "SELL", "NEUTRAL": "WAIT"}.get(signal.direction, "WAIT")
            # A deterministic fallback has no independent AI confidence.
            # Keep it below the risk threshold rather than presenting the
            # deterministic score as if an AI model had confirmed it.
            fallback_confidence = 0.0
            quantity = 1.0 if fallback_decision in {"BUY", "SELL"} else None
            return AITradeDecision(
                snapshot.symbol,
                fallback_decision,
                fallback_confidence,
                "TradingAgents runner not configured; deterministic fallback used",
                "deterministic-fallback",
                quantity=quantity,
                quantity_source="deterministic-fallback" if quantity is not None else None,
            )

        decision = self._decision_from_result(snapshot, self.runner.analyze(payload))
        return self._ensure_ai_sizing(payload, decision)

    def _ensure_ai_sizing(
        self,
        payload: dict[str, Any],
        decision: AITradeDecision,
    ) -> AITradeDecision:
        if self.runner is None or decision.decision not in {"BUY", "SELL"} or decision.quantity is not None:
            return decision

        sizing_payload = dict(payload)
        sizing_payload["task"] = "POSITION_SIZING_ONLY"
        sizing_payload["requested_output"] = {
            "quantity": "REQUIRED positive whole-number share quantity for the confirmed trade",
            "reason": "brief sizing rationale",
        }
        sizing_result = self.runner.analyze(sizing_payload)
        quantity = self._optional_float(sizing_result, "quantity", "shares", "position_size")
        if quantity is None:
            return decision
        sizing_provider = str(sizing_result.get("provider", "tradingagents")).strip() or "tradingagents"
        return AITradeDecision(
            decision.symbol,
            decision.decision,
            decision.confidence,
            decision.rationale,
            f"{decision.provider}|sizing:{sizing_provider}",
            quantity=quantity,
            entry_price=decision.entry_price,
            stop_price=decision.stop_price,
            target_price=decision.target_price,
            quantity_source=f"ai:{sizing_provider}",
        )

    def revise(
        self,
        snapshot: SignalSnapshot,
        signal: DeterministicSignal,
        previous: AITradeDecision,
        risk_feedback: str,
    ) -> AITradeDecision:
        """Give the configured AI one risk-aware setup revision, never a risk bypass."""
        if self.runner is None or previous.decision not in {"BUY", "SELL"}:
            return previous
        previous_levels = None
        if previous.entry_price is not None and previous.stop_price is not None and previous.target_price is not None:
            previous_levels = (previous.entry_price, previous.stop_price, previous.target_price)
        payload = self._build_payload(
            snapshot,
            signal,
            risk_feedback=risk_feedback,
            previous_levels=previous_levels,
        )
        decision = self._decision_from_result(snapshot, self.runner.analyze(payload))
        return self._ensure_ai_sizing(payload, decision)
