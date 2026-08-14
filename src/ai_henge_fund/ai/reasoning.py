"""Provider-neutral research context and prompt construction.

This module deliberately does not call an LLM or broker. It defines the
contract that TradingAgents/OpenAI can consume later while keeping source
signals immutable and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SignalResearchContext:
    """Immutable research context derived from a normalized signal."""

    symbol: str
    action: str
    confidence: Decimal | None
    target_price: Decimal | None
    reasoning: str | None
    source: str
    source_signal_id: str | None


def build_research_prompt(context: SignalResearchContext) -> str:
    """Build a deterministic prompt contract for a future research agent."""
    confidence = str(context.confidence) if context.confidence is not None else "UNKNOWN"
    target = str(context.target_price) if context.target_price is not None else "UNKNOWN"
    reasoning = context.reasoning or "No source reasoning supplied."
    return (
        "Analyze the following trading signal as research input only. "
        "Do not place orders and do not invent missing market data.\n\n"
        f"symbol={context.symbol}\n"
        f"action={context.action}\n"
        f"confidence={confidence}\n"
        f"target_price={target}\n"
        f"source={context.source}\n"
        f"source_signal_id={context.source_signal_id or 'UNKNOWN'}\n"
        f"source_reasoning={reasoning}"
    )
