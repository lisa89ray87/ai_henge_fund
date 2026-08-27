from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.signal_engine.deterministic import DeterministicSignal
from ai_henge_fund.tradingagents.adapter import AITradeDecision


@dataclass(frozen=True)
class RiskDecision:
    action: str
    quantity: float
    risk_per_share: float | None
    reason: str
    checks: tuple[str, ...]
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None


class RiskGate:
    """Fail-closed gate between AI analysis and paper execution."""

    def __init__(
        self,
        *,
        max_position_value: float = 10_000.0,
        min_ai_confidence: float = 0.70,
        allowed_market_states: Iterable[str] = ("REGULAR", "PRE_MARKET", "AFTER_HOURS"),
        reward_risk_multiple: float = 2.0,
    ) -> None:
        if max_position_value <= 0:
            raise ValueError("max_position_value must be greater than zero")
        if not 0 <= min_ai_confidence <= 1:
            raise ValueError("min_ai_confidence must be between 0 and 1")
        if reward_risk_multiple <= 0:
            raise ValueError("reward_risk_multiple must be greater than zero")
        self.max_position_value = max_position_value
        self.min_ai_confidence = min_ai_confidence
        self.allowed_market_states = frozenset(allowed_market_states)
        self.reward_risk_multiple = reward_risk_multiple

    @staticmethod
    def _trade_levels(snapshot: SignalSnapshot, direction: str) -> tuple[float, float, float]:
        """Build a deterministic entry/stop/target plan from recent candles."""
        entry = float(snapshot.last_price)
        candles = snapshot.candles[-5:]
        lows = [float(c["low"]) for c in candles if c.get("low") is not None]
        highs = [float(c["high"]) for c in candles if c.get("high") is not None]
        if direction == "BUY":
            if not lows:
                raise ValueError("Recent low data unavailable for LONG stop")
            stop = min(lows)
            if stop >= entry:
                raise ValueError("LONG stop is not below entry")
            target = entry + (entry - stop) * 2.0
        else:
            if not highs:
                raise ValueError("Recent high data unavailable for SHORT stop")
            stop = max(highs)
            if stop <= entry:
                raise ValueError("SHORT stop is not above entry")
            target = entry - (stop - entry) * 2.0
        return entry, stop, target

    def evaluate(
        self,
        snapshot: SignalSnapshot,
        signal: DeterministicSignal,
        ai: AITradeDecision,
    ) -> RiskDecision:
        checks: list[str] = []

        if not snapshot.is_usable:
            return RiskDecision("WAIT", 0, None, "Market snapshot is not usable", tuple(checks))
        checks.append("DATA_USABLE")

        if snapshot.data_quality not in {"LIVE", "VERIFIED"}:
            return RiskDecision("WAIT", 0, None, "Market data quality is insufficient", tuple(checks))
        checks.append("DATA_QUALITY")

        if snapshot.market_state not in self.allowed_market_states:
            return RiskDecision("WAIT", 0, None, f"Market state {snapshot.market_state!r} is not tradable", tuple(checks))
        checks.append("MARKET_STATE")

        if signal.setup_state != "CANDIDATE":
            return RiskDecision("WAIT", 0, None, "Deterministic setup is not a trade candidate", tuple(checks))
        checks.append("DETERMINISTIC_SETUP")

        expected = "BUY" if signal.direction == "LONG" else "SELL" if signal.direction == "SHORT" else "WAIT"
        if ai.decision != expected:
            return RiskDecision("WAIT", 0, None, "AI decision does not confirm deterministic direction", tuple(checks))
        checks.append("AI_DIRECTION")

        if ai.confidence < self.min_ai_confidence:
            return RiskDecision("WAIT", 0, None, "AI confidence below risk threshold", tuple(checks))
        checks.append("AI_CONFIDENCE")

        try:
            entry, stop, target = self._trade_levels(snapshot, expected)
        except ValueError as exc:
            return RiskDecision("WAIT", 0, None, str(exc), tuple(checks))
        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            return RiskDecision("WAIT", 0, None, "Invalid trade risk distance", tuple(checks))
        checks.append("TRADE_LEVELS")

        quantity = max(1, int(self.max_position_value // entry))
        if quantity <= 0:
            return RiskDecision("WAIT", 0, None, "Price exceeds maximum position value", tuple(checks))

        checks.append("POSITION_SIZE")
        return RiskDecision(
            expected,
            float(quantity),
            risk_per_share,
            "All risk gates passed",
            tuple(checks),
            entry_price=entry,
            stop_price=stop,
            target_price=target,
        )
