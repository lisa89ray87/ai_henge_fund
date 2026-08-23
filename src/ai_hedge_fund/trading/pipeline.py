from __future__ import annotations

from dataclasses import dataclass

from ai_hedge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_hedge_fund.portfolio.manager import PositionManager
from ai_hedge_fund.paper_trading.engine import PaperTradingEngine
from ai_hedge_fund.paper_trading.lifecycle import PaperTradeLifecycle, TradeLifecycleResult
from ai_hedge_fund.risk.gate import RiskDecision, RiskGate
from ai_hedge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_hedge_fund.tradingagents.adapter import TradingAgentsAdapter


@dataclass(frozen=True)
class PipelineResult:
    deterministic_direction: str
    ai_decision: str
    risk: RiskDecision
    lifecycle: TradeLifecycleResult | None


class TradingPipeline:
    """Single orchestration boundary from market evidence to paper execution."""

    def __init__(
        self,
        *,
        signal_engine: DeterministicSignalEngine | None = None,
        ai_adapter: TradingAgentsAdapter | None = None,
        risk_gate: RiskGate | None = None,
        positions: PositionManager | None = None,
        paper_engine: PaperTradingEngine | None = None,
        telegram=None,
    ) -> None:
        self.signal_engine = signal_engine or DeterministicSignalEngine()
        self.ai_adapter = ai_adapter or TradingAgentsAdapter()
        self.risk_gate = risk_gate or RiskGate()
        self.positions = positions or PositionManager()
        self.lifecycle = PaperTradeLifecycle(paper_engine or PaperTradingEngine(), self.positions, telegram)

    def evaluate(self, snapshot: SignalSnapshot) -> PipelineResult:
        signal = self.signal_engine.evaluate(snapshot)
        ai = self.ai_adapter.analyze(snapshot, signal)
        risk = self.risk_gate.evaluate(snapshot, signal, ai)

        lifecycle = None
        if risk.action in {"BUY", "SELL"} and risk.quantity > 0:
            lifecycle = self.lifecycle.open(
                symbol=snapshot.symbol,
                side=risk.action,
                quantity=risk.quantity,
                price=float(snapshot.last_price),
            )

        return PipelineResult(signal.direction, ai.decision, risk, lifecycle)
