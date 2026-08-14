"""Research-only orchestration for normalized AI Henge Fund signals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ai_henge_fund.ai.reasoning import SignalResearchContext, build_research_prompt
from ai_henge_fund.ai.risk import RiskDecision, evaluate_risk


@dataclass(frozen=True, slots=True)
class AnalysisDecision:
    """Auditable result of the research and risk boundary."""

    symbol: str
    action: str
    research_prompt: str
    risk: RiskDecision
    execution_allowed: bool = False


def analyze_signal(
    *,
    symbol: str,
    action: str,
    confidence: Decimal | None,
    target_price: Decimal | None,
    reasoning: str | None,
    source: str,
    source_signal_id: str | None,
) -> AnalysisDecision:
    """Analyze a signal without calling an LLM or broker and never enable execution."""
    context = SignalResearchContext(
        symbol=symbol.upper(),
        action=action.upper(),
        confidence=confidence,
        target_price=target_price,
        reasoning=reasoning,
        source=source,
        source_signal_id=source_signal_id,
    )
    risk = evaluate_risk(
        action=context.action,
        confidence=context.confidence,
        source=context.source,
        live_trading_enabled=False,
    )
    return AnalysisDecision(
        symbol=context.symbol,
        action=context.action,
        research_prompt=build_research_prompt(context),
        risk=risk,
        execution_allowed=False,
    )
