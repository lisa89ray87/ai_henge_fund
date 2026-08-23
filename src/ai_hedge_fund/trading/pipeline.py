from __future__ import annotations

from dataclasses import dataclass

from ai_hedge_fund.alerts.telegram import TelegramNotifier
from ai_hedge_fund.config.settings import get_settings
from ai_hedge_fund.config.telegram import telegram_config_from_env
from ai_hedge_fund.execution.moomoo_order_monitor import MoomooPaperOrderMonitor
from ai_hedge_fund.execution.moomoo_paper import MoomooPaperExecution
from ai_hedge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_hedge_fund.paper_trading.moomoo_lifecycle import (
    MoomooLifecycleResult,
    MoomooPaperTradeLifecycle,
)
from ai_hedge_fund.portfolio.manager import PositionManager
from ai_hedge_fund.risk.gate import RiskDecision, RiskGate
from ai_hedge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_hedge_fund.tradingagents.adapter import TradingAgentsAdapter


@dataclass(frozen=True)
class PipelineResult:
    deterministic_direction: str
    ai_decision: str
    risk: RiskDecision
    lifecycle: MoomooLifecycleResult | None


class TradingPipeline:
    """Single orchestration boundary from market evidence to Moomoo paper execution."""

    def __init__(
        self,
        *,
        signal_engine: DeterministicSignalEngine | None = None,
        ai_adapter: TradingAgentsAdapter | None = None,
        risk_gate: RiskGate | None = None,
        positions: PositionManager | None = None,
        telegram: TelegramNotifier | None = None,
    ) -> None:
        self.signal_engine = signal_engine or DeterministicSignalEngine()
        self.ai_adapter = ai_adapter or TradingAgentsAdapter()
        self.risk_gate = risk_gate or RiskGate()
        self.positions = positions or PositionManager()
        self.telegram = telegram or TelegramNotifier(telegram_config_from_env())
        self._lifecycle: MoomooPaperTradeLifecycle | None = None

    def _ensure_lifecycle(self) -> MoomooPaperTradeLifecycle:
        if self._lifecycle is None:
            settings = get_settings()
            execution = MoomooPaperExecution(
                host=settings.moomoo_opend_host,
                port=settings.moomoo_opend_port,
            )
            monitor = MoomooPaperOrderMonitor(
                host=settings.moomoo_opend_host,
                port=settings.moomoo_opend_port,
            )
            self._lifecycle = MoomooPaperTradeLifecycle(
                execution,
                monitor,
                self.positions,
                self.telegram,
                fill_timeout_seconds=settings.moomoo_paper_fill_timeout_seconds,
            )
        return self._lifecycle

    def close(self) -> None:
        """Close any Moomoo OpenD contexts opened by this pipeline."""
        if self._lifecycle is not None:
            self._lifecycle.close()
            self._lifecycle = None

    def evaluate(self, snapshot: SignalSnapshot) -> PipelineResult:
        signal = self.signal_engine.evaluate(snapshot)
        ai = self.ai_adapter.analyze(snapshot, signal)
        risk = self.risk_gate.evaluate(snapshot, signal, ai)

        lifecycle = None
        if risk.action == "BUY" and risk.quantity > 0 and self.positions.get(snapshot.symbol) is None:
            lifecycle = self._ensure_lifecycle().open(
                symbol=snapshot.symbol,
                side="BUY",
                quantity=risk.quantity,
                price=float(snapshot.last_price),
            )
        elif risk.action == "SELL" and risk.quantity > 0 and self.positions.get(snapshot.symbol) is not None:
            lifecycle = self._ensure_lifecycle().close_position(
                symbol=snapshot.symbol,
                price=float(snapshot.last_price),
            )

        return PipelineResult(signal.direction, ai.decision, risk, lifecycle)
