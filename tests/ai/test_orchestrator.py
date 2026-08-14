from decimal import Decimal

from ai_henge_fund.ai.orchestrator import analyze_signal
from ai_henge_fund.ai.reasoning import SignalResearchContext, build_research_prompt
from ai_henge_fund.ai.risk import evaluate_risk


def test_research_context_preserves_source_provenance() -> None:
    context = SignalResearchContext(
        symbol="NVDA",
        action="BUY",
        confidence=Decimal("0.90"),
        target_price=Decimal("190.00"),
        reasoning="RISK_OFF; catalyst=earnings",
        source="daily_stock_analyse",
        source_signal_id="signal-123",
    )
    prompt = build_research_prompt(context)
    assert "source=daily_stock_analyse" in prompt
    assert "source_signal_id=signal-123" in prompt
    assert "RISK_OFF; catalyst=earnings" in prompt


def test_risk_gate_rejects_low_confidence_trade() -> None:
    decision = evaluate_risk(
        action="BUY",
        confidence=Decimal("0.59"),
        source="daily_stock_analyse",
    )
    assert decision.approved is False
    assert "below" in decision.reason


def test_risk_gate_never_approves_live_execution() -> None:
    decision = evaluate_risk(
        action="SELL",
        confidence=Decimal("0.90"),
        source="daily_stock_analyse",
        live_trading_enabled=True,
    )
    assert decision.approved is False
    assert "explicit broker execution stage" in decision.reason


def test_orchestrator_is_research_only() -> None:
    decision = analyze_signal(
        symbol="amd",
        action="buy",
        confidence=Decimal("0.90"),
        target_price=Decimal("200"),
        reasoning="RISK_OFF; catalyst=earnings",
        source="daily_stock_analyse",
        source_signal_id="signal-1",
    )
    assert decision.symbol == "AMD"
    assert decision.action == "BUY"
    assert decision.risk.approved is True
    assert decision.execution_allowed is False
