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
    ai_provider: str | None = None
    ai_confidence: float | None = None
    quantity_source: str | None = None


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
        return self._ensure_lifecycle().reconcile_startup()

    def handoff_paper_session(self) -> None:
        if self._lifecycle is not None:
            self._lifecycle.overnight_handoff()

    def close(self):
        if self._lifecycle is not None:
            self._lifecycle.close()
            self._lifecycle = None

    def _deployed_capital(self) -> float:
        return sum(abs(position.quantity) * position.average_price for position in self.positions.all())

    @staticmethod
    def _validated_paper_quantity(ai: AITradeDecision, entry_price: float) -> tuple[float, str] | None:
        """Validate AI-selected size without applying live capital budgets in paper mode."""
        quantity = ai.quantity
        if quantity is None:
            if ai.provider == "deterministic-fallback":
                quantity = 1.0
                source = "deterministic-fallback"
            else:
                return None
        else:
            source = ai.quantity_source or "ai"

        if quantity <= 0 or quantity != int(quantity) or entry_price <= 0:
            return None

        # Paper/simulation deliberately ignores starting capital, maximum deployed
        # capital, risk-per-trade percentage, and daily-loss budgets. Those values
        # are live-trading guardrails, not simulation constraints.
        return float(int(quantity)), f"{source} position size={int(quantity)}"

    def _paper_test_decision(self, snapshot: SignalSnapshot, signal, ai: AITradeDecision) -> RiskDecision:
        """Apply strategy-quality gates in paper mode while bypassing live capital budgets."""
        checks: list[str] = ["PAPER_CAPITAL_LIMITS_BYPASSED"]

        if not snapshot.is_usable:
            return RiskDecision("WAIT", 0, None, "Market snapshot is not usable", tuple(checks))
        if snapshot.data_quality not in {"LIVE", "VERIFIED"}:
            return RiskDecision("WAIT", 0, None, "Market data quality is insufficient", tuple(checks))
        checks.append("DATA_QUALITY")

        if snapshot.market_state not in self.risk_gate.allowed_market_states:
            return RiskDecision("WAIT", 0, None, f"Market state {snapshot.market_state!r} is not tradable", tuple(checks))
        checks.append("MARKET_STATE")

        if signal.setup_state != "CANDIDATE":
            return RiskDecision("WAIT", 0, None, "Deterministic setup is not a trade candidate", tuple(checks))

        expected = "BUY" if signal.direction == "LONG" else "SELL" if signal.direction == "SHORT" else "WAIT"
        if ai.decision != expected or expected == "WAIT":
            return RiskDecision("WAIT", 0, None, "AI decision does not confirm a tradable deterministic direction", tuple(checks))
        checks.append("AI_DIRECTION")

        if ai.confidence < self.risk_gate.min_ai_confidence:
            return RiskDecision("WAIT", 0, None, "AI confidence below risk threshold", tuple(checks))
        checks.append("AI_CONFIDENCE")

        try:
            fallback_entry, fallback_stop, fallback_target = self.risk_gate._trade_levels(snapshot, expected)
        except ValueError as exc:
            return RiskDecision("WAIT", 0, None, str(exc), tuple(checks))

        entry = ai.entry_price if ai.entry_price is not None else fallback_entry
        stop = ai.stop_price if ai.stop_price is not None else fallback_stop
        target = ai.target_price if ai.target_price is not None else fallback_target

        if expected == "BUY":
            valid_levels = stop < entry < target
        else:
            valid_levels = target < entry < stop
        if not valid_levels:
            return RiskDecision("WAIT", 0, None, "AI trade levels are invalid for the selected direction", tuple(checks))

        risk_per_share = abs(entry - stop)
        reward_per_share = abs(target - entry)
        reward_risk = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0
        if reward_risk < self.risk_gate.reward_risk_multiple:
            return RiskDecision(
                "WAIT", 0, risk_per_share,
                f"Reward/risk {reward_risk:.2f} is below minimum {self.risk_gate.reward_risk_multiple:.2f}",
                tuple(checks), entry_price=entry, stop_price=stop, target_price=target,
            )
        checks.extend(["AI_TRADE_LEVELS", "REWARD_RISK"])

        validated = self._validated_paper_quantity(ai, entry)
        if validated is None:
            reason = "AI did not provide a valid paper position size"
            return RiskDecision(
                "WAIT", 0, risk_per_share, reason,
                tuple(checks + ["AI_POSITION_SIZE_REQUIRED"]),
                entry_price=entry, stop_price=stop, target_price=target,
            )
        quantity, size_check = validated
        checks.append("AI_POSITION_SIZE")

        return RiskDecision(
            expected,
            quantity,
            risk_per_share,
            f"Paper strategy gates passed; live capital gate bypassed; {size_check}",
            tuple(checks),
            entry_price=entry,
            stop_price=stop,
            target_price=target,
        )

    def analyze(self, snapshot: SignalSnapshot) -> PipelineResult:
        signal = self.signal_engine.evaluate(snapshot)
        ai = self.ai_adapter.analyze(snapshot, signal)
        settings = get_settings()
        if not settings.moomoo_live_trading_enabled:
            risk = self._paper_test_decision(snapshot, signal, ai)
        else:
            risk = self.risk_gate.evaluate(
                snapshot, signal, ai,
                deployed_capital=self._deployed_capital(),
                open_position_count=len(self.positions.all()),
            )
        return PipelineResult(
            signal.direction, ai.decision, risk, None,
            ai_provider=ai.provider,
            ai_confidence=ai.confidence,
            quantity_source=ai.quantity_source,
        )

    def execute_paper_result(self, snapshot: SignalSnapshot, result: PipelineResult) -> PipelineResult:
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
            result.deterministic_direction, result.ai_decision, result.risk, lifecycle,
            ai_provider=result.ai_provider,
            ai_confidence=result.ai_confidence,
            quantity_source=result.quantity_source,
        )

    def evaluate(self, snapshot: SignalSnapshot, *, execute_paper: bool = True) -> PipelineResult:
        result = self.analyze(snapshot)
        if execute_paper:
            return self.execute_paper_result(snapshot, result)
        return result
