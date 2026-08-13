"""Provider-neutral decision context assembled from existing signals and live data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ai_henge_fund.agents.moomoo_bridge import QuoteSnapshot


@dataclass(frozen=True)
class DecisionContext:
    """Stable input contract for TradingAgents and the future risk engine."""

    symbol: str
    source: str
    source_signal_id: str | None
    action: str
    confidence: float | None
    target_price: float | None
    reasoning: str | None
    quote: QuoteSnapshot | None = None

    def to_request(self) -> dict[str, Any]:
        """Return a JSON-friendly, provider-neutral decision request."""
        result = asdict(self)
        result["quote"] = asdict(self.quote) if self.quote is not None else None
        if self.quote is not None and self.quote.timestamp is not None:
            result["quote"]["timestamp"] = self.quote.timestamp.isoformat()
        return result


def build_decision_context(signal: Any, quote: QuoteSnapshot | None = None) -> DecisionContext:
    """Combine an AI Henge Fund signal with optional Moomoo quote data."""
    return DecisionContext(
        symbol=str(signal.symbol).upper(),
        source=str(signal.source),
        source_signal_id=signal.source_signal_id,
        action=signal.action.value if hasattr(signal.action, "value") else str(signal.action),
        confidence=float(signal.confidence) if signal.confidence is not None else None,
        target_price=float(signal.target_price) if signal.target_price is not None else None,
        reasoning=signal.reasoning,
        quote=quote,
    )
