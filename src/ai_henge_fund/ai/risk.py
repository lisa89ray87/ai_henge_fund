"""Deterministic pre-trade risk gate.

The gate is intentionally conservative and does not submit orders. It is a
safety boundary between research output and any future broker adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str


def evaluate_risk(
    *,
    action: str,
    confidence: Decimal | None,
    source: str,
    live_trading_enabled: bool = False,
    minimum_confidence: Decimal = Decimal("0.60"),
) -> RiskDecision:
    """Return a deterministic approval decision without executing anything."""
    normalized_action = action.strip().upper()
    if normalized_action not in {"BUY", "SELL", "HOLD"}:
        return RiskDecision(False, "Unsupported action")
    if normalized_action == "HOLD":
        return RiskDecision(True, "HOLD requires no trade")
    if not source.strip():
        return RiskDecision(False, "Signal source is required")
    if confidence is None:
        return RiskDecision(False, "Confidence is required for BUY/SELL")
    if confidence < minimum_confidence:
        return RiskDecision(False, "Confidence is below the minimum risk threshold")
    if not live_trading_enabled:
        return RiskDecision(True, "Research approved; live trading is disabled")
    return RiskDecision(False, "Live trading requires an explicit broker execution stage")
