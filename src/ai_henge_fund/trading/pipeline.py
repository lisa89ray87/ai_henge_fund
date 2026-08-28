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
from ai_henge_fund.tradingagents.adapter import AITradeDecision, TradingAgentsAdapter


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

    @staticmethod
    def _validated_paper_quantity(ai: AITradeDecision, entry_price: float) -> tuple[float, str] | None:
        """Validate AI-selected size without re-enabling the live RiskGate.

        Paper mode exercises AI sizing, but still rejects impossible quantities.
        The deterministic fallback intentionally uses one share so provider
        outages do not silently turn into an oversized paper position.
        """
        quantity = ai.quantity
        if quantity is None:
            if ai.provider == "deterministic-fallback":
                quantity = 1.0
            else:
                return None
        if quantity <= 0:
            return None
        if quantity != int(quantity):
            return None
        if entry_price <= 0:
            return None
        settings = get_settings()
        max_deployed = settings.ai_henge_fund_max_capital_deployed
        max_by_capital = int(max_deployed // entry_price)
        quantity = min(float(int(quantity)), float(max_by_capital))
        if quantity <= 0:
            return None
        return quantity, f"AI-selected quantity={int(quantity)}"

    def _paper_test_decision(self, snapshot: SignalSnapshot, signal, ai: AITradeDecision) -> RiskDecision:
        """Build an execution decision without applying the live-capital risk gate."""
        expected = "BUY" if signal.direction == "LONG" else "SELL" if signal.direction == "SHORT" else "WAIT"
        if ai.decision != expected or expected == "WAIT":
            return RiskDecision(
                "WAIT", 0, None, "AI decision does not confirm a tradable deterministic direction", ("PAPER_RISK_BYPASS",),
            )

        try:
            fallback_entry, fallback_stop, fallback_target = self.risk_gate._trade_levels(snapshot, expected)
        except ValueError as exc:
            return RiskDecision("WAIT", 0, None, str(exc), ("PAPER_RISK_BYPASS",))

        entry = ai.entry_price if ai.entry_price is not None else fallback_entry
        stop = ai.stop_price if ai.stop_price is not None else fallback_stop
        target = ai.target_price if ai.target_price is not None else fallback_target

        if expected == "BUY":
            valid_levels = stop < entry < target
        else:
            valid_levels = target < entry < stop
        if not valid_levels:
            return RiskDecision("WAIT", 0, None, "AI trade levels are invalid for the selected direction", ("PAPER_RISK_BYPASS",))

        validated = self._validated_paper_quantity(ai, entry)
        if validated is None:
            return RiskDecision(
                "WAIT", 0, None,
                "AI did not provide a valid paper position size",
                ("PAPER_RISK_BYPASS", "AI_POSITION_SIZE_REQUIRED"),
                entry_price=entry, stop_price=stop, target_price=target,
            )
        quantity, size_check = validated

        return RiskDecision(
            expected,
            quantity,
            abs(entry - stop),
            f"Paper-only mode: capital risk gate bypassed; {size_check}",
            ("PAPER_RISK_BYPASS", "AI_POSITION_SIZE", "AI_TRADE_LEVELS"),
            entry_price=entry,
            stop_price=stop,
            target_price=target,
        )

    def analyze(self, snapshot: SignalSnapshot) -> PipelineResult:
        """Run signal + AI + risk evaluation without placing a paper order.

        This separation is intentional: the AI call can be time-bounded by the
        session runner without allowing a late-returning AI thread to submit an
        order after its timeout has already been reported.
        """
        signal = self.signal_engine.evaluate(snapshot)
        ai = self.ai_adapter.analyze(snapshot, signal)
        settings = get_settings()

        if not settings.moomoo_live_trading_enabled:
            risk = self._paper_test_decision(snapshot, signal, ai)
        else:
            risk = self.risk_gate.evaluate(
                snapshot,
                signal,
                ai,
                deployed_capital=self._deployed_capital(),
                open_position_count=len(self.positions.all()),
            )

        return PipelineResult(signal.direction, ai.decision, risk, None)

    def execute_paper_result(self, snapshot: SignalSnapshot, result: PipelineResult) -> PipelineResult:
        """Execute an already-completed, validated paper decision.

        Kept separate from ``analyze`` so a timed-out AI analysis cannot place a
        paper order after the runner has moved on.
        """
        lifecycle = None
        if result.risk.action in {"BUY", "SELL"} and result.risk.quantity > 0:
            existing = self.positions.get(snapshot.symbol)
            if existing is None:
                lifecycle = self._ensure_lifecycle().open(
                    symbol=snapshot.symbol,
                    side=result.risk.action,
                    quantity=result.risk.quantity,
                    price=result.risk.entry_price or float(snapshot.last_price),
                    stop_price=result.risk.stop_price,
                    target_price=result.risk.target_price,
                )
            else:
                existing_side = "BUY" if existing.quantity > 0 else "SELL"
                if result.risk.action != existing_side:
                    lifecycle = self._ensure_lifecycle().close_position(
                        symbol=snapshot.symbol,
                        price=float(snapshot.last_price),
                    )
        return PipelineResult(
            result.deterministic_direction,
            result.ai_decision,
            result.risk,
            lifecycle,
        )

    def evaluate(self, snapshot: SignalSnapshot, *, execute_paper: bool = True) -> PipelineResult:
        """Backward-compatible combined analysis and optional paper execution."""
        result = self.analyze(snapshot)
        if execute_paper:
            return self.execute_paper_result(snapshot, result)
        return result
