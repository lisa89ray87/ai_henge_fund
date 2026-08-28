from __future__ import annotations

from dataclasses import dataclass

from ai_henge_fund.alerts.telegram import TelegramNotifier
from ai_henge_fund.config.settings import get_settings
from ai_henge_fund.config.telegram import telegram_config_from_env
from ai_henge_fund.execution.moomoo_order_monitor import MoomooPaperOrderMonitor
from ai_henge_fund.execution.moomoo_paper import MoomooPaperExecution
from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooLifecycleResult, MoomooPaperTradeLifecycle
from ai_henge_fund.portfolio.manager import PositionManager
from ai_henge_fund.risk.gate import RiskDecision, RiskGate
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_henge_fund.tradingagents.adapter import TradingAgentsAdapter


@dataclass(frozen=True)
class PipelineResult:
    deterministic_direction: str
    ai_decision: str
    risk: RiskDecision
    lifecycle: MoomooLifecycleResult | None


class TradingPipeline:
    """Single orchestration boundary from market evidence to Moomoo paper execution."""

    def __init__(self, *, signal_engine=None, ai_adapter=None, risk_gate=None, positions=None, telegram=None):
        self.signal_engine = signal_engine or DeterministicSignalEngine()
        self.ai_adapter = ai_adapter or TradingAgentsAdapter()
        self.risk_gate = risk_gate or RiskGate()
        self.positions = positions or PositionManager()
        self.telegram = telegram or TelegramNotifier(telegram_config_from_env())
        self._lifecycle = None

    def _ensure_lifecycle(self):
        if self._lifecycle is None:
            settings = get_settings()
            if not settings.moomoo_paper_trading_enabled:
                raise RuntimeError("Moomoo paper trading is disabled in application settings.")
            execution = MoomooPaperExecution(host=settings.moomoo_opend_host, port=settings.moomoo_opend_port)
            monitor = MoomooPaperOrderMonitor(host=settings.moomoo_opend_host, port=settings.moomoo_opend_port)
            self._lifecycle = MoomooPaperTradeLifecycle(execution, monitor, self.positions, self.telegram, fill_timeout_seconds=settings.moomoo_paper_fill_timeout_seconds)
        return self._lifecycle

    def resume_paper_session(self) -> int:
        """Reconcile Moomoo positions and restore saved protection at session start."""
        return self._ensure_lifecycle().reconcile_startup()

    def handoff_paper_session(self) -> None:
        """Stop agent-side protection and hand overnight responsibility to the user."""
        if self._lifecycle is not None:
            self._lifecycle.overnight_handoff()

    def close(self):
        if self._lifecycle is not None:
            self._lifecycle.close()
            self._lifecycle = None

    def _deployed_capital(self) -> float:
        """Calculate current strategy deployment from reconstructed paper positions."""
        return sum(abs(position.quantity) * position.average_price for position in self.positions.all())

    def evaluate(self, snapshot: SignalSnapshot, *, execute_paper: bool = True) -> PipelineResult:
        signal = self.signal_engine.evaluate(snapshot)
        ai = self.ai_adapter.analyze(snapshot, signal)
        risk = self.risk_gate.evaluate(
            snapshot,
            signal,
            ai,
            deployed_capital=self._deployed_capital(),
            open_position_count=len(self.positions.all()),
        )
        lifecycle = None
        if execute_paper and risk.action in {"BUY", "SELL"} and risk.quantity > 0:
            existing = self.positions.get(snapshot.symbol)
            if existing is None:
                lifecycle = self._ensure_lifecycle().open(
                    symbol=snapshot.symbol,
                    side=risk.action,
                    quantity=risk.quantity,
                    price=risk.entry_price or float(snapshot.last_price),
                    stop_price=risk.stop_price,
                    target_price=risk.target_price,
                )
            elif risk.action == "SELL" and existing.quantity > 0:
                lifecycle = self._ensure_lifecycle().close_position(symbol=snapshot.symbol, price=float(snapshot.last_price))
        return PipelineResult(signal.direction, ai.decision, risk, lifecycle)
